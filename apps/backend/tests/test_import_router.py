import io
import json
import zipfile

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.catalog.application.service import RoleWithCount
from api.catalog.domain.entities import Question
from api.catalog.domain.entities import Role as CatalogRole
from api.importing.application.service import ImportService, ImportSummary
from api.importing.domain import InvalidImportError
from api.importing.presentation import router as import_router_module
from api.importing.presentation.errors import register_importing_exception_handlers
from api.importing.presentation.router import import_router
from iam import (
    ActiveUserData,
    JwtService,
    Role,
    register_iam_exception_handlers,
)

SECRET = "test-secret-key-at-least-32-bytes"

SUMMARY = ImportSummary(
    roles_created=5,
    questions_created=6,
    candidates_created=2,
    answers_imported=2,
    scoring_jobs_queued=1,
    audio_answers_needing_person=1,
)


class FakeImportService:
    def __init__(self, *, error: InvalidImportError | None = None) -> None:
        self._error = error
        self.data: bytes | None = None

    async def import_zip(self, data: bytes, owner_id: int) -> ImportSummary:
        self.data = data
        if self._error is not None:
            raise self._error
        return SUMMARY


def _app(service: object) -> tuple[FastAPI, JwtService]:
    jwt_service = JwtService(secret=SECRET)
    app = FastAPI()
    app.state.jwt_service = jwt_service
    app.state.import_service = service
    register_iam_exception_handlers(app)
    register_importing_exception_handlers(app)
    app.include_router(import_router)
    return app, jwt_service


def _token(jwt_service: JwtService, role: Role = Role.HR) -> str:
    return jwt_service.sign_access_token(
        ActiveUserData(sub=1, email="hr@example.com", role=role),
    )


def _headers(jwt_service: JwtService, role: Role = Role.HR) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(jwt_service, role)}"}


async def test_import_returns_summary() -> None:
    service = FakeImportService()
    app, jwt_service = _app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            headers=_headers(jwt_service),
            files={"file": ("pack.zip", b"\x50\x4b\x03\x04", "application/zip")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "roles_created": 5,
        "questions_created": 6,
        "candidates_created": 2,
        "answers_imported": 2,
        "scoring_jobs_queued": 1,
        "audio_answers_needing_person": 1,
    }
    assert service.data == b"\x50\x4b\x03\x04"


async def test_import_invalid_zip_400() -> None:
    service = FakeImportService(error=InvalidImportError("not a valid zip archive"))
    app, jwt_service = _app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            headers=_headers(jwt_service),
            files={"file": ("pack.zip", b"garbage", "application/zip")},
        )

    assert response.status_code == 400
    assert response.json() == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "not a valid zip archive",
    }


async def test_import_too_large_413(monkeypatch) -> None:
    monkeypatch.setattr(import_router_module, "MAX_IMPORT_BYTES", 4)
    service = FakeImportService()
    app, jwt_service = _app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            headers=_headers(jwt_service),
            files={"file": ("pack.zip", b"\x50\x4b\x03\x04\x05", "application/zip")},
        )

    assert response.status_code == 413
    assert service.data is None


async def test_import_requires_authentication() -> None:
    service = FakeImportService()
    app, _ = _app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            files={"file": ("pack.zip", b"\x50\x4b", "application/zip")},
        )

    assert response.status_code == 401


async def test_import_requires_hr_role() -> None:
    service = FakeImportService()
    app, jwt_service = _app(service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            headers=_headers(jwt_service, Role.REGULAR),
            files={"file": ("pack.zip", b"\x50\x4b", "application/zip")},
        )

    assert response.status_code == 403


class _MinimalCatalog:
    def __init__(self) -> None:
        self._roles: dict[str, CatalogRole] = {}
        self._next_role_id = 1

    async def list_questions(self) -> list[Question]:
        return []

    async def list_roles(self, owner_id: int) -> list[RoleWithCount]:
        return [RoleWithCount(role=role, candidate_count=0) for role in self._roles.values()]

    async def ensure_role(self, name: str) -> CatalogRole:
        if name not in self._roles:
            self._roles[name] = CatalogRole(id=self._next_role_id, name=name)
            self._next_role_id += 1
        return self._roles[name]

    async def upsert_question(
        self,
        *,
        code: str,
        sort_order: int,
        prompt: str,
        grading_guide: dict[str, str],
    ) -> Question:
        return Question(
            id=0,
            code=code,
            sort_order=sort_order,
            prompt=prompt,
            grading_guide=grading_guide,
        )


def _malformed_pack() -> bytes:
    files = {
        "questions.md": b"# Interview questions\n",
        "pipeline_log.csv": (
            b"candidate_id,candidate_name,candidate_email,role\n"
            b"C2041,Nhi Van Tran,nhi@example.com,Backend Engineer\n"
        ),
        "answers/A001.json": json.dumps(
            {
                "answer_id": "A001",
                "candidate_id": "C2041",
                "role": "Backend Engineer",
                "question_id": "Q1",
                "transcript": "hi",
            }
        ).encode("utf-8"),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def test_import_malformed_answer_json_400() -> None:
    # The malformed record fails before candidates/answers/file_storage are used,
    # so only the catalog is exercised and the rest can be omitted.
    importer = ImportService(_MinimalCatalog(), None, None, None)
    app, jwt_service = _app(importer)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/hr/import",
            headers=_headers(jwt_service),
            files={"file": ("pack.zip", _malformed_pack(), "application/zip")},
        )

    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Bad Request"
    assert body["status"] == 400
    assert body["detail"] == "answer record missing required field 'submitted_at'"
