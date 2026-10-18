import pytest
from api.candidates.infrastructure.storage import LocalFileStorage


async def test_save_and_read_roundtrip(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)

    await storage.save("audio/7/3.m4a", b"\x00\x01\x02")

    assert await storage.read("audio/7/3.m4a") == b"\x00\x01\x02"


async def test_delete_removes(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    await storage.save("audio/7/3.m4a", b"payload")

    await storage.delete("audio/7/3.m4a")

    with pytest.raises(FileNotFoundError):
        await storage.read("audio/7/3.m4a")
