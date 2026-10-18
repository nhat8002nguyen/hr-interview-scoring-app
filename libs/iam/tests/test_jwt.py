import jwt
import pytest
from iam.application.jwt import JwtService

from iam import ActiveUserData, Role, UnauthorizedError


def _user() -> ActiveUserData:
    return ActiveUserData(
        sub=10,
        email="a@example.com",
        role=Role.REGULAR,
        group_ids=frozenset({5, 1}),
    )


def test_access_token_round_trips_claims() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-bytes")

    token = service.sign_access_token(_user())
    verified = service.verify_access_token(token)

    assert verified == _user()


def test_refresh_token_is_rejected_as_an_access_token() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-bytes")
    refresh = service.sign_refresh_token(user_id=10, jti="jti-1")

    with pytest.raises(UnauthorizedError, match="Invalid access token"):
        service.verify_access_token(refresh)


def test_refresh_token_round_trips_sub_and_jti() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-bytes")

    token = service.sign_refresh_token(user_id=10, jti="jti-1")
    claims = service.verify_refresh_token(token)

    assert claims.sub == 10
    assert claims.jti == "jti-1"


def test_expired_access_token_is_rejected() -> None:
    service = JwtService(
        secret="test-secret-key-at-least-32-bytes",
        access_token_ttl_seconds=-1,
    )
    token = service.sign_access_token(_user())

    with pytest.raises(UnauthorizedError, match="Invalid access token"):
        service.verify_access_token(token)


def test_tampered_token_is_rejected() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-bytes")
    token = service.sign_access_token(_user())
    other = jwt.encode({"sub": "10", "token_type": "access"}, "other-secret", algorithm="HS256")

    with pytest.raises(UnauthorizedError):
        service.verify_access_token(token + "x")
    with pytest.raises(UnauthorizedError, match="Invalid access token"):
        service.verify_access_token(other)
