from datetime import datetime
from typing import Protocol

from api.scoring.domain.entities import ScoringInput, ScoringJob, ScoringJobSummary


class ScoringJobRepository(Protocol):
    async def get(self, job_id: int) -> ScoringJob | None: ...

    async def get_owned(self, job_id: int, owner_id: int) -> ScoringJob | None: ...

    async def get_by_answer(self, answer_id: int) -> ScoringJob | None: ...

    async def upsert_for_answer(self, answer_id: int, status: str) -> ScoringJob: ...

    async def claim_next_queued(self, now: datetime) -> ScoringJob | None: ...

    async def mark_scored(
        self,
        job_id: int,
        *,
        suggested_score: int,
        suggested_reasoning: str,
        now: datetime,
    ) -> ScoringJob: ...

    async def record_failure(
        self,
        job_id: int,
        *,
        error: str,
        now: datetime,
        max_attempts: int,
    ) -> ScoringJob: ...

    async def set_override(
        self,
        answer_id: int,
        *,
        final_score: int,
        override_reason: str,
        overridden_by: int,
        now: datetime,
    ) -> ScoringJob: ...

    async def mark_retried(self, job_id: int, *, now: datetime) -> ScoringJob: ...

    async def list(self, status: str | None, owner_id: int) -> list[ScoringJobSummary]: ...

    async def reset_stale_claims(self, before: datetime) -> int: ...

    async def load_scoring_input(self, answer_id: int) -> ScoringInput | None: ...
