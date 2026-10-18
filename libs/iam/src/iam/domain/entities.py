from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    HR = "hr"
    REGULAR = "regular"


class AuthType(StrEnum):
    JWT = "jwt"
    API_KEY = "api_key"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class AccessScope:
    user_id: int
    group_ids: frozenset[int] = frozenset()
    is_admin: bool = False

    def can_access(self, owner_id: int, group_id: int | None) -> bool:
        if self.is_admin or self.user_id == owner_id:
            return True
        return group_id is not None and group_id in self.group_ids

    def can_assign_group(self, group_id: int | None) -> bool:
        if group_id is None or self.is_admin:
            return True
        return group_id in self.group_ids


@dataclass(frozen=True, slots=True)
class ActiveUserData:
    sub: int
    email: str
    role: Role
    group_ids: frozenset[int] = frozenset()

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def to_access_scope(self) -> AccessScope:
        return AccessScope(
            user_id=self.sub,
            group_ids=self.group_ids,
            is_admin=self.is_admin,
        )


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    uuid: str
    api_key: str
    hashed_key: str


@dataclass(frozen=True, slots=True)
class StoredApiKey:
    id: int
    uuid: str
    hashed_key: str
    user_id: int
    label: str
    created_at: datetime
