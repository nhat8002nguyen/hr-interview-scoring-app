from api.importing.application.service import ImportSummary
from api.importing.domain import InvalidImportError
from api.importing.presentation import router as import_router_module
from api.importing.presentation.errors import register_importing_exception_handlers
from api.importing.presentation.router import import_router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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

    async def import_zip(self, data: bytes) -> ImportSummary:
        self.data = data
        if self._error is not None:
            raise self._error
        return SUMMARY


def _app(service: FakeImportService) -> tuple[FastAPI, JwtService]:
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
