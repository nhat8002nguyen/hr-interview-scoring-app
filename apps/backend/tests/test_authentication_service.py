import pytest
from sqlalchemy.exc import IntegrityError

from api.auth.application.service import AuthenticationService, AuthTokens
from api.auth.domain.entities import User
from api.auth.domain.exceptions import EmailAlreadyExistsError, WeakPasswordError
from iam import ActiveUserData, JwtService, Role, UnauthorizedError

SECRET = "test-secret-key-at-least-32-bytes"
EMAIL = "hr@talotrace.ai"
PASSWORD = "correct-horse-battery-staple"


class _UniqueViolation(Exception):
    pgcode = "23505"


class FakeUserRepository:
    def __init__(
        self,
        *,
        by_email: dict[str, User] | None = None,
        by_id: dict[int, User] | None = None,
        fail_add_with_unique: bool = False,
    ) -> None:
        self._by_email = by_email or {}
        self._by_id = (
            by_id if by_id is not None else {user.id: user for user in self._by_email.values()}
        )
        self._fail_add_with_unique = fail_add_with_unique

    async def add(self, user: User) -> User:
        if self._fail_add_with_unique:
            raise IntegrityError("INSERT", {}, _UniqueViolation())
        self._by_email[user.email] = user
        self._by_id[user.id] = user
        return user

    async def get(self, user_id: int) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)


class FakeHashingService:
    async def hash(self, data: str) -> str:
        return f"hashed:{data}"

    async def compare(self, data: str, hashed: str) -> bool:
        return hashed == f"hashed:{data}"


class FakeRefreshTokenStorage:
    def __init__(self, *, consumed: dict[str, int] | None = None) -> None:
        self.saved: list[tuple[str, int, int]] = []
        self.consume_calls: list[str] = []
        self.revoked: list[str] = []
        self._consumed = consumed or {}

    async def save(self, token_id: str, user_id: int, ttl_seconds: int) -> None:
        self.saved.append((token_id, user_id, ttl_seconds))

    async def validate_and_consume(self, token_id: str) -> int | None:
        self.consume_calls.append(token_id)
        return self._consumed.get(token_id)

    async def revoke(self, token_id: str) -> None:
        self.revoked.append(token_id)


def _jwt() -> JwtService:
    return JwtService(secret=SECRET)


def _user() -> User:
    return User(id=7, email=EMAIL, password_hash=f"hashed:{PASSWORD}", role=Role.HR)


async def test_sign_in_issues_tokens() -> None:
    user = _user()
    jwt_service = _jwt()
    refresh_tokens = FakeRefreshTokenStorage()
    service = AuthenticationService(
        users=FakeUserRepository(by_email={user.email: user}),
        hashing=FakeHashingService(),
        jwt=jwt_service,
        refresh_tokens=refresh_tokens,
    )

    tokens = await service.sign_in(user.email, PASSWORD)

    assert isinstance(tokens, AuthTokens)
    assert tokens.user == user
    assert tokens.access_token
    assert tokens.refresh_token
    assert len(refresh_tokens.saved) == 1

    access = jwt_service.verify_access_token(tokens.access_token)
    assert access == ActiveUserData(
        sub=user.id,
        email=user.email,
        role=user.role,
        group_ids=frozenset(),
    )


async def test_sign_in_rejects_bad_password() -> None:
    user = _user()
    service = AuthenticationService(
        users=FakeUserRepository(by_email={user.email: user}),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(UnauthorizedError, match="Invalid credentials"):
        await service.sign_in(user.email, "wrong-password")


async def test_sign_in_rejects_unknown_email() -> None:
    service = AuthenticationService(
        users=FakeUserRepository(),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(UnauthorizedError, match="Invalid credentials"):
        await service.sign_in("nobody@example.com", PASSWORD)


async def test_refresh_rotates_and_consumes() -> None:
    user = _user()
    jwt_service = _jwt()
    jti = "jti-1"
    refresh_token = jwt_service.sign_refresh_token(user.id, jti)
    refresh_tokens = FakeRefreshTokenStorage(consumed={jti: user.id})
    service = AuthenticationService(
        users=FakeUserRepository(by_id={user.id: user}),
        hashing=FakeHashingService(),
        jwt=jwt_service,
        refresh_tokens=refresh_tokens,
    )

    tokens = await service.refresh(refresh_token)

    assert refresh_tokens.consume_calls == [jti]
    assert tokens.user == user
    assert len(refresh_tokens.saved) == 1
    assert refresh_tokens.saved[0][1] == user.id


async def test_sign_out_revokes() -> None:
    user = _user()
    jwt_service = _jwt()
    jti = "jti-2"
    refresh_token = jwt_service.sign_refresh_token(user.id, jti)
    refresh_tokens = FakeRefreshTokenStorage()
    service = AuthenticationService(
        users=FakeUserRepository(),
        hashing=FakeHashingService(),
        jwt=jwt_service,
        refresh_tokens=refresh_tokens,
    )

    await service.sign_out(refresh_token)

    assert refresh_tokens.revoked == [jti]


async def test_sign_out_without_token_is_noop() -> None:
    refresh_tokens = FakeRefreshTokenStorage()
    service = AuthenticationService(
        users=FakeUserRepository(),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=refresh_tokens,
    )

    await service.sign_out(None)

    assert refresh_tokens.revoked == []


async def test_sign_up_creates_hr_and_issues_tokens() -> None:
    users = FakeUserRepository()
    refresh_tokens = FakeRefreshTokenStorage()
    service = AuthenticationService(
        users=users,
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=refresh_tokens,
    )

    tokens = await service.sign_up("new@example.com", "password123")

    assert tokens.user.role == Role.HR
    assert tokens.user.email == "new@example.com"

    stored = await users.get_by_email("new@example.com")
    assert stored is not None
    assert stored.role == Role.HR
    assert stored.password_hash == "hashed:password123"

    assert len(refresh_tokens.saved) == 1
    assert refresh_tokens.saved[0][1] == tokens.user.id


async def test_sign_up_duplicate_email_raises() -> None:
    existing = User(id=7, email="new@example.com", password_hash="hashed:x", role=Role.HR)
    service = AuthenticationService(
        users=FakeUserRepository(by_email={existing.email: existing}),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(EmailAlreadyExistsError):
        await service.sign_up("new@example.com", "password123")


async def test_sign_up_unique_violation_on_add_maps_to_conflict() -> None:
    service = AuthenticationService(
        users=FakeUserRepository(fail_add_with_unique=True),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(EmailAlreadyExistsError):
        await service.sign_up("race@example.com", "password123")


async def test_sign_up_then_sign_in_with_different_email_casing() -> None:
    users = FakeUserRepository()
    service = AuthenticationService(
        users=users,
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    signed_up = await service.sign_up("  Alex@Acme.com ", "password123")
    signed_in = await service.sign_in("alex@acme.com", "password123")

    assert signed_up.user.email == "alex@acme.com"
    assert signed_in.user.email == "alex@acme.com"
    stored = await users.get_by_email("alex@acme.com")
    assert stored is not None
    assert stored.email == "alex@acme.com"


async def test_sign_up_duplicate_email_is_case_insensitive() -> None:
    existing = User(id=7, email="alex@acme.com", password_hash="hashed:x", role=Role.HR)
    service = AuthenticationService(
        users=FakeUserRepository(by_email={existing.email: existing}),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(EmailAlreadyExistsError):
        await service.sign_up("Alex@Acme.com", "password123")


async def test_sign_up_short_password_raises() -> None:
    service = AuthenticationService(
        users=FakeUserRepository(),
        hashing=FakeHashingService(),
        jwt=_jwt(),
        refresh_tokens=FakeRefreshTokenStorage(),
    )

    with pytest.raises(WeakPasswordError):
        await service.sign_up("new@example.com", "short")
