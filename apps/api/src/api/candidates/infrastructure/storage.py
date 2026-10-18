from pathlib import Path


class LocalFileStorage:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    async def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def _resolve(self, key: str) -> Path:
        path = (self._directory / key).resolve()
        if not path.is_relative_to(self._directory.resolve()):
            raise ValueError(f"Unsafe storage key: {key!r}")
        return path
