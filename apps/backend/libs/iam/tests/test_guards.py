from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from iam.application.jwt import JwtService
from iam.presentation.dependencies import require_auth, require_roles
from iam.presentation.errors import register_iam_exception_handlers

from iam import ActiveUserData, AuthType, Role


class FakeApiKeys:
    def __init__(self, user: ActiveUserData) -> None:
        self.user = user

    async def validate_api_key(self, raw_api_key: str) -> ActiveUserData | None:
        if raw_api_key == "good-key":
            return self.user
        return None


def _user(role: Role = Role.REGULAR) -> ActiveUserData:
    return ActiveUserData(sub=10, email="a@example.com", role=role, group_ids=frozenset({5}))


def _app() -> tuple[FastAPI, JwtService]:
    jwt_service = JwtService(secret="test-secret-key-at-least-32-bytes")
    app = FastAPI()
    app.state.jwt_service = jwt_service
    app.state.api_key_validator = FakeApiKeys(_user())
    register_iam_exception_handlers(app)

    @app.get("/open", dependencies=[Depends(require_auth(AuthType.NONE))])
    async def open_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/either", dependencies=[Depends(require_auth(AuthType.JWT, AuthType.API_KEY))])
    async def either_route() -> dict[str, bool]:
        return {"ok": True}

    @app.delete("/admin", dependencies=[Depends(require_roles(Role.ADMIN))])
    async def admin_route() -> dict[str, bool]:
        return {"ok": True}

    return app, jwt_service


async def test_missing_credentials_are_unauthorized() -> None:
    app, _ = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/either")

    assert response.status_code == 401
    assert response.json()["title"] == "Unauthorized"


async def test_bearer_and_api_key_both_authenticate() -> None:
    app, jwt_service = _app()
    token = jwt_service.sign_access_token(_user())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bearer = await client.get("/either", headers={"Authorization": f"Bearer {token}"})
        api_key = await client.get("/either", headers={"api_key": "good-key"})

    assert bearer.status_code == 200
    assert api_key.status_code == 200


async def test_public_route_allows_anonymous_calls() -> None:
    app, _ = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/open")

    assert response.status_code == 200


async def test_regular_user_cannot_call_an_admin_route() -> None:
    app, jwt_service = _app()
    token = jwt_service.sign_access_token(_user(Role.REGULAR))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/admin", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role permissions"


async def test_admin_can_call_an_admin_route() -> None:
    app, jwt_service = _app()
    token = jwt_service.sign_access_token(_user(Role.ADMIN))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/admin", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
