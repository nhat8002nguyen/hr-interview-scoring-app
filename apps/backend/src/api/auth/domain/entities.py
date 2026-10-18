from dataclasses import dataclass

from iam import Role


@dataclass(frozen=True, slots=True)
class User:
    id: int
    email: str
    password_hash: str
    role: Role
