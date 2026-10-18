"""End-to-end import and scoring test against a real PostgreSQL.

Spins up an ephemeral ``postgres:18-alpine`` container, imports the real
business-systems pack, drains the scoring queue through the real worker with a
fake LLM, and asserts the exact import summary counts and resulting scoring-job
states. The test is skipped cleanly when Docker is unavailable.
"""

import asyncio
import io
import secrets
import shutil
import socket
import subprocess
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import api.auth.infrastructure.models  # noqa: F401 - register UserModel, RefreshTokenModel
import api.candidates.infrastructure.models  # noqa: F401 - register CandidateModel, AnswerModel
import api.catalog.infrastructure.models  # noqa: F401 - register RoleModel, QuestionModel
import api.scoring.infrastructure.models  # noqa: F401 - register ScoringJobModel
import asyncpg
import pytest
from api.candidates.application.service import AnswersService, CandidatesService
from api.candidates.infrastructure.models import AnswerModel, CandidateModel
from api.candidates.infrastructure.storage import LocalFileStorage
from api.candidates.infrastructure.unit_of_work import CandidatesUnitOfWork
from api.catalog.application.service import CatalogService
from api.catalog.infrastructure.models import QuestionModel, RoleModel
from api.catalog.infrastructure.unit_of_work import CatalogUnitOfWork
from api.importing.application.service import ImportService
from api.scoring.application.ports import LlmScore
from api.scoring.application.service import ScoringService
from api.scoring.application.worker import ScoringWorker
from api.scoring.infrastructure.models import ScoringJobModel
from api.scoring.infrastructure.unit_of_work import SqlAlchemyScoringUnitOfWork
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database import Base, create_engine, create_session_factory

_PACK_DIR = (
    Path(__file__).resolve().parents[3].parent / "intial-resources" / "business-systems-pack"
)

_POSTGRES_USER = "postgres"
_POSTGRES_PASSWORD = "postgres"
_POSTGRES_DB = "talot_e2e"
_POSTGRES_IMAGE = "postgres:18-alpine"

# The pack holds 35 answer records, but candidate C2052 recorded question Q3
# twice (A022 then A023, a retake). The answers table has a unique constraint on
# (candidate_id, question_id), so the import merges those two records into one
# row: the later record wins and the version is bumped. The summary still counts
# every record (35 answers, 30 text jobs queued), but the database ends up with
# 29 text answers and 5 audio answers.
_TEXT_ANSWER_ROWS = 29
_AUDIO_ANSWER_ROWS = 5


@dataclass(frozen=True, slots=True)
class _PostgresContainer:
    container_id: str
    host: str
    port: int

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}"
            f"@{self.host}:{self.port}/{_POSTGRES_DB}"
        )


@dataclass(frozen=True, slots=True)
class _JobState:
    answer_type: str
    status: str
    suggested_score: int | None
    final_score: int | None


class FakeLlm:
    async def score(
        self,
        prompt: str,
        grading_guide: dict[str, str],
        answer_text: str,
    ) -> LlmScore:
        return LlmScore(3, "meets the bar")


def _docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_pack_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(_PACK_DIR / "questions.md", "questions.md")
        archive.write(_PACK_DIR / "pipeline_log.csv", "pipeline_log.csv")
        for path in sorted((_PACK_DIR / "answers").iterdir()):
            archive.write(path, f"answers/{path.name}")
    return buffer.getvalue()


async def _wait_until_ready(container: _PostgresContainer, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            connection = await asyncpg.connect(
                host=container.host,
                port=container.port,
                user=_POSTGRES_USER,
                password=_POSTGRES_PASSWORD,
                database=_POSTGRES_DB,
            )
            await connection.close()
            return
        except Exception as exc:  # noqa: BLE001 - readiness probing across retries
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Postgres never became ready: {exc}") from exc
            await asyncio.sleep(0.5)


async def _queued_job_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ScoringJobModel)
            .where(ScoringJobModel.status == "queued")
        )
    return int(count or 0)


async def _fetch_jobs(session_factory: async_sessionmaker[AsyncSession]) -> list[_JobState]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(
                    AnswerModel.answer_type,
                    ScoringJobModel.status,
                    ScoringJobModel.suggested_score,
                    ScoringJobModel.final_score,
                )
                .select_from(ScoringJobModel)
                .join(AnswerModel, ScoringJobModel.answer_id == AnswerModel.id)
            )
        ).all()
    return [
        _JobState(row.answer_type, row.status, row.suggested_score, row.final_score) for row in rows
    ]


@pytest.fixture
def postgres_container() -> Iterator[_PostgresContainer]:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not found; skipping Postgres end-to-end test")
    if _docker(["info"]).returncode != 0:
        pytest.skip("docker daemon is not running; skipping Postgres end-to-end test")

    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--rm",
            "-e",
            f"POSTGRES_USER={_POSTGRES_USER}",
            "-e",
            f"POSTGRES_PASSWORD={_POSTGRES_PASSWORD}",
            "-e",
            f"POSTGRES_DB={_POSTGRES_DB}",
            "-p",
            f"{port}:5432",
            _POSTGRES_IMAGE,
        ]
    )
    if started.returncode != 0:
        pytest.skip(f"could not start {_POSTGRES_IMAGE}: {started.stderr.strip()}")

    container_id = started.stdout.strip()
    try:
        yield _PostgresContainer(container_id=container_id, host="127.0.0.1", port=port)
    finally:
        _docker(["rm", "-f", container_id])


async def test_import_and_score_end_to_end(
    tmp_path: Path,
    postgres_container: _PostgresContainer,
) -> None:
    await _wait_until_ready(postgres_container)

    engine = create_engine(postgres_container.url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = create_session_factory(engine)

        candidates = CandidatesService(
            lambda: CandidatesUnitOfWork(session_factory),
            token_generator=lambda: secrets.token_urlsafe(32),
        )
        catalog = CatalogService(
            lambda: CatalogUnitOfWork(session_factory),
            counter=candidates,
        )
        scoring = ScoringService(lambda: SqlAlchemyScoringUnitOfWork(session_factory))
        file_storage = LocalFileStorage(tmp_path)
        answers = AnswersService(
            lambda: CandidatesUnitOfWork(session_factory),
            catalog,
            scoring,
            file_storage,
        )
        importing = ImportService(catalog, candidates, answers, file_storage)

        summary = await importing.import_zip(_build_pack_zip())
        assert summary.roles_created == 5
        assert summary.questions_created == 6
        assert summary.candidates_created == 18
        assert summary.answers_imported == 35
        assert summary.scoring_jobs_queued == 30
        assert summary.audio_answers_needing_person == 5

        # Re-importing the same pack must not overcount the merged retake
        # (C2052 answered Q3 twice: A022 then A023). The surviving row keeps
        # A022's external_ref, so A023 is re-processed but unchanged and must
        # not be reported as newly imported or re-queued.
        second = await importing.import_zip(_build_pack_zip())
        assert second.roles_created == 0
        assert second.questions_created == 0
        assert second.candidates_created == 0
        assert second.answers_imported == 0
        assert second.scoring_jobs_queued == 0
        assert second.audio_answers_needing_person == 0

        stop_event = asyncio.Event()
        worker = ScoringWorker(
            lambda: SqlAlchemyScoringUnitOfWork(session_factory),
            FakeLlm(),
            max_attempts=3,
            poll_interval_seconds=0,
            stop_event=stop_event,
        )
        task = asyncio.create_task(worker.run())
        try:
            deadline = time.monotonic() + 30.0
            while await _queued_job_count(session_factory) > 0:
                if time.monotonic() >= deadline:
                    raise TimeoutError("scoring queue did not drain within 30s")
                await asyncio.sleep(0.05)
        finally:
            stop_event.set()
            await task

        jobs = await _fetch_jobs(session_factory)
        text_jobs = [job for job in jobs if job.answer_type == "text"]
        audio_jobs = [job for job in jobs if job.answer_type == "audio"]

        assert len(jobs) == _TEXT_ANSWER_ROWS + _AUDIO_ANSWER_ROWS
        assert len(text_jobs) == _TEXT_ANSWER_ROWS
        assert len(audio_jobs) == _AUDIO_ANSWER_ROWS
        assert all(job.status == "scored" for job in text_jobs)
        assert all(job.suggested_score == 3 and job.final_score == 3 for job in text_jobs)
        assert all(job.status == "needs_a_person" for job in audio_jobs)
        assert all(job.final_score is None for job in audio_jobs)
        assert all(job.status != "failed" for job in jobs)

        # A duplicate byte-identical submission must be a no-op: the answer keeps
        # its version and the already-scored job is not re-queued.
        existing = await answers.get_by_external_ref("A001")
        assert existing is not None and existing.answer_type == "text"
        assert existing.text is not None
        before_version = existing.version

        result = await answers.submit_text(
            existing.candidate_id,
            existing.question_id,
            existing.text,
        )

        assert result.unchanged is True
        assert result.answer.version == before_version
        after_job = await scoring.get_job_by_answer(existing.id)
        assert after_job.status == "scored"
        assert after_job.suggested_score == 3
        assert after_job.final_score == 3
    finally:
        await engine.dispose()


async def test_claim_is_exclusive(
    postgres_container: _PostgresContainer,
) -> None:
    await _wait_until_ready(postgres_container)

    engine = create_engine(postgres_container.url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = create_session_factory(engine)

        async with session_factory() as session:
            role = RoleModel(name="Backend Engineer")
            session.add(role)
            await session.flush()
            question = QuestionModel(
                code="Q1",
                sort_order=1,
                prompt="Tell us about a piece of work.",
                grading_guide={"1": "No", "4": "Yes"},
            )
            session.add(question)
            await session.flush()
            candidate = CandidateModel(
                name="Ada",
                email="ada@example.com",
                role_id=role.id,
                session_token="token-1",
            )
            session.add(candidate)
            await session.flush()
            answer = AnswerModel(
                candidate_id=candidate.id,
                question_id=question.id,
                answer_type="text",
                text="hello",
                content_hash="abc123",
                version=1,
                submitted_at=datetime.now(UTC),
            )
            session.add(answer)
            await session.flush()
            session.add(ScoringJobModel(answer_id=answer.id, status="queued"))
            await session.commit()

        def uow_factory() -> SqlAlchemyScoringUnitOfWork:
            return SqlAlchemyScoringUnitOfWork(session_factory)

        async with uow_factory() as uow:
            first = await uow.scoring_jobs.claim_next_queued(datetime.now(UTC))
        assert first is not None

        async with uow_factory() as uow:
            second = await uow.scoring_jobs.claim_next_queued(datetime.now(UTC))
        assert second is None
    finally:
        await engine.dispose()
