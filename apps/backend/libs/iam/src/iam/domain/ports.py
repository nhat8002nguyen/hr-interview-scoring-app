from typing import Protocol

from iam.domain.entities import ActiveUserData


class HashingServiceProtocol(Protocol):
    async def hash(self, data: str) -> str: ...

    async def compare(self, data: str, hashed: str) -> bool: ...


class RefreshTokenStorageProtocol(Protocol):
    async def save(self, token_id: str, user_id: int, ttl_seconds: int) -> None: ...

    async def validate_and_consume(self, token_id: str) -> int | None: ...

    async def revoke(self, token_id: str) -> None: ...


class ApiKeyValidatorProtocol(Protocol):
    async def validate_api_key(self, raw_api_key: str) -> ActiveUserData | None: ...
