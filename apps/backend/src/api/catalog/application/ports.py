from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from api.catalog.domain.repositories import QuestionRepository, RoleRepository


class RoleCandidateCounter(Protocol):
    async def count_by_role(self, role_id: int, owner_id: int) -> int: ...


class CatalogUnitOfWorkPort(Protocol):
    roles: RoleRepository
    questions: QuestionRepository


CatalogUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[CatalogUnitOfWorkPort]]
