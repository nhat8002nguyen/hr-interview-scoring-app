import asyncio
import hashlib

import bcrypt


class BcryptHashingService:
    async def hash(self, data: str) -> str:
        return await asyncio.to_thread(_hash, data)

    async def compare(self, data: str, hashed: str) -> bool:
        return await asyncio.to_thread(_compare, data, hashed)


def _digest(data: str) -> bytes:
    return hashlib.sha256(data.encode()).digest()


def _hash(data: str) -> str:
    return bcrypt.hashpw(_digest(data), bcrypt.gensalt()).decode()


def _compare(data: str, hashed: str) -> bool:
    return bcrypt.checkpw(_digest(data), hashed.encode())
