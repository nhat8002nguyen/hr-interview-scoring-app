from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from api.auth.domain.entities import User
from api.auth.domain.exceptions import EmailAlreadyExistsError, UserNotFoundError, WeakPasswordError
from api.auth.domain.repositories import UserRepository
from iam import (
    ActiveUserData,
    HashingServiceProtocol,
    JwtService,
    RefreshTokenStorageProtocol,
    Role,
    UnauthorizedError,
)

_UNIQUE_VIOLATION = "23505"


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    if orig is None:
        return False
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code == _UNIQUE_VIOLATION


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True, slots=True)
class AuthTokens:
    user: User
    access_token: str
    refresh_token: str


class AuthenticationService:
    def __init__(
        self,
        users: UserRepository,
        hashing: HashingServiceProtocol,
        jwt: JwtService,
        refresh_tokens: RefreshTokenStorageProtocol,
        min_password_length: int = 8,
    ) -> None:
        self._users = users
        self._hashing = hashing
        self._jwt = jwt
        self._refresh_tokens = refresh_tokens
        self._min_password_length = min_password_length

    async def sign_in(self, email: str, password: str) -> AuthTokens:
        email = _normalize_email(email)
        user = await self._users.get_by_email(email)
        if user is None or not await self._hashing.compare(password, user.password_hash):
            raise UnauthorizedError("Invalid credentials")
        return await self._issue_tokens(user)

    async def sign_up(self, email: str, password: str) -> AuthTokens:
        email = _normalize_email(email)
        if len(password) < self._min_password_length:
            raise WeakPasswordError(self._min_password_length)
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyExistsError(email)
        password_hash = await self._hashing.hash(password)
        try:
            user = await self._users.add(
                User(id=0, email=email, password_hash=password_hash, role=Role.HR)
            )
        except IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
            raise EmailAlreadyExistsError(email) from None
        return await self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> AuthTokens:
        claims = self._jwt.verify_refresh_token(refresh_token)
        user_id = await self._refresh_tokens.validate_and_consume(claims.jti)
        if user_id is None or user_id != claims.sub:
            raise UnauthorizedError("Refresh token is no longer valid")
        user = await self._users.get(claims.sub)
        if user is None:
            raise UserNotFoundError(claims.sub)
        return await self._issue_tokens(user)

    async def sign_out(self, refresh_token: str | None) -> None:
        if refresh_token is None:
            return
        try:
            claims = self._jwt.verify_refresh_token(refresh_token)
        except UnauthorizedError:
            return
        await self._refresh_tokens.revoke(claims.jti)

    async def _issue_tokens(self, user: User) -> AuthTokens:
        token_id = str(uuid4())
        active_user = ActiveUserData(
            sub=user.id,
            email=user.email,
            role=user.role,
            group_ids=frozenset(),
        )
        await self._refresh_tokens.save(
            token_id,
            user.id,
            self._jwt.refresh_token_ttl_seconds,
        )
        return AuthTokens(
            user=user,
            access_token=self._jwt.sign_access_token(active_user),
            refresh_token=self._jwt.sign_refresh_token(user.id, token_id),
        )
