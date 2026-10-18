from iam.application.api_key import ApiKeyService
from iam.application.hashing import BcryptHashingService


async def test_create_and_hash_embeds_the_uuid() -> None:
    service = ApiKeyService(BcryptHashingService())

    generated = await service.create_and_hash("11111111-1111-1111-1111-111111111111")

    assert generated.uuid == "11111111-1111-1111-1111-111111111111"
    assert service.extract_uuid_from_api_key(generated.api_key) == generated.uuid
    assert await service.validate(generated.api_key, generated.hashed_key) is True
    assert await service.validate("not-the-key", generated.hashed_key) is False


def test_extract_uuid_rejects_malformed_keys() -> None:
    service = ApiKeyService(BcryptHashingService())

    assert service.extract_uuid_from_api_key("%%%") is None
    assert service.extract_uuid_from_api_key("") is None
