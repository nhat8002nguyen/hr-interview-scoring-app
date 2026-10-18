import pytest
from api.catalog.application.service import RoleWithCount
from api.catalog.domain.entities import Role as CatalogRole
from api.catalog.domain.exceptions import QuestionNotFoundError, RoleNotFoundError
from api.catalog.presentation.errors import register_catalog_exception_handlers
from api.catalog.presentation.router import catalog_router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from iam import (
    ActiveUserData,
    JwtService,
    Role,
    register_iam_exception_handlers,
)

SECRET = "test-secret-key-at-least-32-bytes"


class FakeCatalogService:
    def __init__(self) -> None:
        self.list_roles_calls = 0

    async def list_roles(self) -> list[RoleWithCount]:
        self.list_roles_calls += 1
        return [
            RoleWithCount(
                role=CatalogRole(id=1, name="Backend Engineer"),
                candidate_count=3,
            ),
            RoleWithCount(
                role=CatalogRole(id=2, name="Sales Executive"),
                candidate_count=0,
            ),
        ]


def _app(service: FakeCatalogService) -> tuple[FastAPI, JwtService]:
    jwt_service = JwtService(secret=SECRET)
    app = FastAPI()
    app.state.jwt_service = jwt_service
    app.state.catalog_service = service
    register_iam_exception_handlers(app)
    register_catalog_exception_handlers(app)
    app.include_router(catalog_router)
    return app, jwt_service


def _access_token(jwt_service: JwtService, role: Role) -> str:
    return jwt_service.sign_access_token(ActiveUserData(sub=1, email="hr@example.com", role=role))


async def test_list_roles_returns_counts_for_hr() -> None:
    service = FakeCatalogService()
    app, jwt_service = _app(service)
    token = _access_token(jwt_service, Role.HR)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/hr/roles",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "Backend Engineer", "candidate_count": 3},
        {"id": 2, "name": "Sales Executive", "candidate_count": 0},
    ]
    assert service.list_roles_calls == 1


async def test_list_roles_without_token_is_unauthorized() -> None:
    service = FakeCatalogService()
    app, _ = _app(service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/hr/roles")

    assert response.status_code == 401
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Unauthorized"
    assert body["status"] == 401
    assert service.list_roles_calls == 0


async def test_list_roles_with_non_hr_token_is_forbidden() -> None:
    service = FakeCatalogService()
    app, jwt_service = _app(service)
    token = _access_token(jwt_service, Role.REGULAR)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/hr/roles",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Forbidden"
    assert body["status"] == 403
    assert service.list_roles_calls == 0


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (QuestionNotFoundError(99), "Question #99 not found"),
        (RoleNotFoundError(5), "Role #5 not found"),
    ],
)
async def test_catalog_not_found_returns_problem_details(
    error: Exception,
    detail: str,
) -> None:
    app, _ = _app(FakeCatalogService())

    @app.get("/missing")
    async def missing() -> None:
        raise error

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": detail,
    }
