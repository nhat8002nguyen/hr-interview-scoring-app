import base64
from uuid import uuid4

from iam.domain.entities import GeneratedApiKey
from iam.domain.ports import HashingServiceProtocol


class ApiKeyService:
    def __init__(self, hashing: HashingServiceProtocol) -> None:
        self._hashing = hashing

    async def create_and_hash(self, key_uuid: str) -> GeneratedApiKey:
        raw_key = base64.b64encode(f"{key_uuid}:{uuid4()}".encode()).decode()
        hashed_key = await self._hashing.hash(raw_key)
        return GeneratedApiKey(uuid=key_uuid, api_key=raw_key, hashed_key=hashed_key)

    def extract_uuid_from_api_key(self, raw_key: str) -> str | None:
        try:
            decoded = base64.b64decode(raw_key, validate=True).decode()
        except ValueError, UnicodeDecodeError:
            return None
        key_uuid, separator, secret = decoded.partition(":")
        if separator != ":" or not key_uuid or not secret:
            return None
        return key_uuid

    async def validate(self, raw_key: str, hashed_key: str) -> bool:
        return await self._hashing.compare(raw_key, hashed_key)
