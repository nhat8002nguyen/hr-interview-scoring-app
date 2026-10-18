from typing import Protocol

from api.auth.domain.entities import User


class UserRepository(Protocol):
    async def add(self, user: User) -> User: ...

    async def get(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...
