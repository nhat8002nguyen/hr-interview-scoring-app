import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from api.candidates.application.ports import FileStorage
from api.candidates.application.service import AnswersService, CandidatesService
from api.candidates.domain.entities import Candidate
from api.catalog.application.service import CatalogService
from api.catalog.domain.entities import Role
from api.importing.domain import InvalidImportError


@dataclass(frozen=True, slots=True)
class ImportSummary:
    roles_created: int
    questions_created: int
    candidates_created: int
    answers_imported: int
    scoring_jobs_queued: int
    audio_answers_needing_person: int


@dataclass(frozen=True, slots=True)
class _QuestionSpec:
    code: str
    sort_order: int
    prompt: str
    grading_guide: dict[str, str]


@dataclass(frozen=True, slots=True)
class _AnswerRecord:
    payload: dict[str, object]
    audio_bytes: bytes | None


_QUESTION_HEADING = re.compile(r"^##\s+([A-Z]\d+)\.\s*(.*)$")
_BULLET = re.compile(r"^-\s+\*\*([1-4]):\*\*\s*(.*)$")
_OPEN_ROLES = re.compile(r"^Open roles:\s*(.*)$")


def _parse_questions(markdown: str) -> tuple[list[_QuestionSpec], list[str]]:
    specs: list[_QuestionSpec] = []
    open_roles: list[str] = []
    current_code: str | None = None
    current_prompt = ""
    bullets: dict[str, str] = {}

    for line in markdown.splitlines():
        open_roles_match = _OPEN_ROLES.match(line)
        if open_roles_match:
            raw = open_roles_match.group(1).rstrip(".")
            open_roles = [role.strip() for role in raw.split(",") if role.strip()]
            continue

        heading = _QUESTION_HEADING.match(line)
        if heading:
            if current_code is not None:
                specs.append(
                    _QuestionSpec(
                        code=current_code,
                        sort_order=int(current_code[1:]),
                        prompt=current_prompt,
                        grading_guide=bullets,
                    )
                )
            current_code = heading.group(1)
            current_prompt = heading.group(2).strip()
            bullets = {}
            continue

        bullet = _BULLET.match(line)
        if bullet is not None and current_code is not None:
            bullets[bullet.group(1)] = bullet.group(2).strip()

    if current_code is not None:
        specs.append(
            _QuestionSpec(
                code=current_code,
                sort_order=int(current_code[1:]),
                prompt=current_prompt,
                grading_guide=bullets,
            )
        )

    return specs, open_roles


def _parse_pipeline(csv_text: str) -> dict[str, tuple[str, str, str]]:
    pipeline: dict[str, tuple[str, str, str]] = {}
    try:
        for row in csv.DictReader(io.StringIO(csv_text)):
            candidate_id = (row.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            pipeline[candidate_id] = (
                (row.get("candidate_name") or "").strip(),
                (row.get("candidate_email") or "").strip(),
                (row.get("role") or "").strip(),
            )
    except csv.Error as exc:
        raise InvalidImportError("malformed pipeline_log.csv") from exc
    return pipeline


def _required(payload: dict[str, object], key: str) -> object:
    if key not in payload:
        raise InvalidImportError(f"answer record missing required field {key!r}")
    return payload[key]


def _parse_submitted_at(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise InvalidImportError(f"invalid submitted_at value {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _read_pack(data: bytes) -> tuple[str, str, list[_AnswerRecord]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InvalidImportError("not a valid zip archive") from exc

    with archive:
        names = set(archive.namelist())
        for member in ("questions.md", "pipeline_log.csv"):
            if member not in names:
                raise InvalidImportError(f"missing required member {member!r}")

        try:
            questions_md = archive.read("questions.md").decode("utf-8")
            pipeline_csv = archive.read("pipeline_log.csv").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidImportError("pack text members must be UTF-8") from exc

        answer_members = sorted(
            name for name in names if name.startswith("answers/") and name.endswith(".json")
        )
        records: list[_AnswerRecord] = []
        for name in answer_members:
            try:
                payload = json.loads(archive.read(name).decode("utf-8"))
            except ValueError as exc:
                raise InvalidImportError(f"malformed answer member {name!r}") from exc
            if not isinstance(payload, dict):
                raise InvalidImportError(f"answer member {name!r} must be a JSON object")
            audio_bytes: bytes | None = None
            audio_file = payload.get("audio_file")
            if audio_file:
                audio_name = f"answers/{audio_file}"
                if audio_name not in names:
                    raise InvalidImportError(f"missing audio member {audio_name!r}")
                audio_bytes = archive.read(audio_name)
            records.append(_AnswerRecord(payload=payload, audio_bytes=audio_bytes))

    return questions_md, pipeline_csv, records


def _collect_roles(
    open_roles: list[str],
    pipeline: dict[str, tuple[str, str, str]],
    records: list[_AnswerRecord],
) -> list[str]:
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    for name in open_roles:
        add(name)
    for _, _, role in pipeline.values():
        add(role)
    for record in records:
        role_value = record.payload.get("role")
        if isinstance(role_value, str):
            add(role_value)
    return names


class ImportService:
    def __init__(
        self,
        catalog: CatalogService,
        candidates: CandidatesService,
        answers: AnswersService,
        file_storage: FileStorage,
    ) -> None:
        self._catalog = catalog
        self._candidates = candidates
        self._answers = answers
        self._file_storage = file_storage

    async def import_zip(self, data: bytes, owner_id: int) -> ImportSummary:
        questions_md, pipeline_csv, records = _read_pack(data)

        question_specs, open_roles = _parse_questions(questions_md)
        pipeline = _parse_pipeline(pipeline_csv)
        role_names = _collect_roles(open_roles, pipeline, records)

        existing_codes = {question.code for question in await self._catalog.list_questions()}
        questions_created = 0
        for spec in question_specs:
            if spec.code not in existing_codes:
                questions_created += 1
            await self._catalog.upsert_question(
                code=spec.code,
                sort_order=spec.sort_order,
                prompt=spec.prompt,
                grading_guide=spec.grading_guide,
            )

        role_by_name = {
            listed.role.name: listed.role for listed in await self._catalog.list_roles(owner_id)
        }
        roles_created = 0
        for name in role_names:
            if name not in role_by_name:
                role_by_name[name] = await self._catalog.ensure_role(name)
                roles_created += 1

        questions_by_code = {
            question.code: question for question in await self._catalog.list_questions()
        }

        candidates_created = 0
        answers_imported = 0
        scoring_jobs_queued = 0
        audio_answers_needing_person = 0

        for record in records:
            payload = record.payload
            answer_id = str(_required(payload, "answer_id"))
            candidate_ref = str(_required(payload, "candidate_id"))
            question_code = str(_required(payload, "question_id"))
            submitted_at = _parse_submitted_at(_required(payload, "submitted_at"))

            question = questions_by_code.get(question_code)
            if question is None:
                raise InvalidImportError(f"unknown question code {question_code!r}")

            candidate = await self._candidates.get_by_external_ref(owner_id, candidate_ref)
            if candidate is None:
                candidate = await self._create_candidate(
                    candidate_ref,
                    payload,
                    pipeline,
                    role_by_name,
                    owner_id,
                )
                candidates_created += 1

            transcript = payload.get("transcript")
            audio_file = payload.get("audio_file")

            if isinstance(transcript, str):
                if await self._answers.get_by_external_ref(candidate.id, answer_id) is not None:
                    continue
                _, changed = await self._answers.import_answer(
                    candidate.id,
                    question.id,
                    answer_type="text",
                    text=transcript,
                    audio_key=None,
                    content_hash=sha256(transcript.encode("utf-8")).hexdigest(),
                    external_ref=answer_id,
                    submitted_at=submitted_at,
                )
                if changed:
                    answers_imported += 1
                    scoring_jobs_queued += 1
            elif transcript is None and audio_file and record.audio_bytes is not None:
                if await self._answers.get_by_external_ref(candidate.id, answer_id) is not None:
                    continue
                key = f"audio/import/{answer_id}.m4a"
                await self._file_storage.save(key, record.audio_bytes)
                _, changed = await self._answers.import_answer(
                    candidate.id,
                    question.id,
                    answer_type="audio",
                    text=None,
                    audio_key=key,
                    content_hash=sha256(record.audio_bytes).hexdigest(),
                    external_ref=answer_id,
                    submitted_at=submitted_at,
                )
                if changed:
                    answers_imported += 1
                    audio_answers_needing_person += 1

        return ImportSummary(
            roles_created=roles_created,
            questions_created=questions_created,
            candidates_created=candidates_created,
            answers_imported=answers_imported,
            scoring_jobs_queued=scoring_jobs_queued,
            audio_answers_needing_person=audio_answers_needing_person,
        )

    async def _create_candidate(
        self,
        candidate_ref: str,
        payload: dict[str, object],
        pipeline: dict[str, tuple[str, str, str]],
        role_by_name: dict[str, Role],
        owner_id: int,
    ) -> Candidate:
        pipeline_row = pipeline.get(candidate_ref)
        if pipeline_row is not None:
            name, email, role_name = pipeline_row
            role_name = role_name or str(payload.get("role") or "")
        else:
            name = candidate_ref
            email = f"{candidate_ref.lower()}@import.local"
            role_name = str(payload.get("role") or "")

        role = role_by_name.get(role_name)
        if role is None:
            raise InvalidImportError(f"unknown role {role_name!r} for candidate {candidate_ref!r}")

        return await self._candidates.create_candidate(
            name=name,
            email=email,
            role_id=role.id,
            owner_id=owner_id,
            external_ref=candidate_ref,
        )
