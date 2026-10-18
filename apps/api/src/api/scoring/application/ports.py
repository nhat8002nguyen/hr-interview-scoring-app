"""Ports for the scoring application layer.

The worker consumes :class:`ScoringLlmPort` to ask an LLM to score a candidate
answer. Infrastructure adapters (for example the DeepSeek client) implement it.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol, Self

from api.scoring.domain.repositories import ScoringJobRepository


class ScoringUnitOfWork(Protocol):
    scoring_jobs: ScoringJobRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None: ...


ScoringUnitOfWorkFactory = Callable[
    [], AbstractAsyncContextManager[ScoringUnitOfWork]
]


@dataclass(frozen=True, slots=True)
class LlmScore:
    score: int
    reasoning: str


class LlmError(Exception):
    """Base error for LLM transport failures."""


class LlmValidationError(LlmError):
    """Raised when the LLM response is not a valid, well-formed score."""


class ScoringLlmPort(Protocol):
    async def score(
        self,
        prompt: str,
        grading_guide: dict[str, str],
        answer_text: str,
    ) -> LlmScore: ...
