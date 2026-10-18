from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Role:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class Question:
    id: int
    code: str
    sort_order: int
    prompt: str
    grading_guide: dict[str, str]
