from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from iam.domain.entities import ActiveUserData, Role
from iam.domain.exceptions import UnauthorizedError


@dataclass(frozen=True, slots=True)
class RefreshTokenClaims:
    sub: int
    jti: str


class JwtService:
    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        access_token_ttl_seconds: int = 3600,
        refresh_token_ttl_seconds: int = 86400,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = access_token_ttl_seconds
        self._refresh_ttl = refresh_token_ttl_seconds

    @property
    def refresh_token_ttl_seconds(self) -> int:
        return self._refresh_ttl

    def sign_access_token(self, user: ActiveUserData) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.sub),
            "email": user.email,
            "role": str(user.role),
            "group_ids": sorted(user.group_ids),
            "token_type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=self._access_ttl),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def sign_refresh_token(self, user_id: int, jti: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "jti": jti,
            "token_type": "refresh",
            "iat": now,
            "exp": now + timedelta(seconds=self._refresh_ttl),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify_access_token(self, token: str) -> ActiveUserData:
        payload = self._decode(token, "Invalid access token")
        if payload.get("token_type") != "access":
            raise UnauthorizedError("Invalid access token")
        try:
            sub = payload["sub"]
            email = payload["email"]
            role = payload["role"]
            group_ids = payload["group_ids"]
            if (
                not isinstance(sub, (str, int))
                or not isinstance(email, str)
                or not isinstance(role, str)
                or not isinstance(group_ids, list)
                or not all(isinstance(group_id, (str, int)) for group_id in group_ids)
            ):
                raise ValueError
            return ActiveUserData(
                sub=int(sub),
                email=email,
                role=Role(role),
                group_ids=frozenset(int(group_id) for group_id in group_ids),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedError("Invalid access token") from exc

    def verify_refresh_token(self, token: str) -> RefreshTokenClaims:
        payload = self._decode(token, "Invalid refresh token")
        jti = payload.get("jti")
        if payload.get("token_type") != "refresh" or not isinstance(jti, str) or not jti:
            raise UnauthorizedError("Invalid refresh token")
        try:
            sub = payload["sub"]
            if not isinstance(sub, (str, int)):
                raise ValueError
            return RefreshTokenClaims(sub=int(sub), jti=jti)
        except (KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedError("Invalid refresh token") from exc

    def _decode(self, token: str, message: str) -> dict[str, object]:
        try:
            decoded = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(message) from exc
        if not isinstance(decoded, dict):
            raise UnauthorizedError(message)
        return decoded
