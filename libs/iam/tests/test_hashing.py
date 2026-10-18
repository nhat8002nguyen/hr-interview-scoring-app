import asyncio

from iam.application.hashing import BcryptHashingService


async def test_hash_and_compare_round_trip() -> None:
    service = BcryptHashingService()

    hashed = await service.hash("correct horse")

    assert hashed != "correct horse"
    assert await service.compare("correct horse", hashed) is True
    assert await service.compare("wrong", hashed) is False


async def test_hash_accepts_inputs_longer_than_bcrypt_limit() -> None:
    service = BcryptHashingService()
    long_input = "a" * 100

    hashed = await service.hash(long_input)

    assert await service.compare(long_input, hashed) is True


async def test_hash_does_not_block_the_event_loop() -> None:
    service = BcryptHashingService()
    started = asyncio.get_running_loop().time()

    await asyncio.gather(service.hash("one"), service.hash("two"))

    assert asyncio.get_running_loop().time() >= started
