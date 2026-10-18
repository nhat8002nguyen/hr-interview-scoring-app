from api.candidates.application.ports import ScoringSnapshot
from api.scoring.application.service import ScoringService
from api.scoring.domain.exceptions import ScoringJobNotFoundError


class ScoringServiceReader:
    """Adapts :class:`ScoringService` to the candidate-layer ``ScoringReader`` port."""

    def __init__(self, scoring: ScoringService) -> None:
        self._scoring = scoring

    async def get_snapshot(self, answer_id: int) -> ScoringSnapshot | None:
        try:
            job = await self._scoring.get_job_by_answer(answer_id)
        except ScoringJobNotFoundError:
            return None
        return ScoringSnapshot(
            status=job.status,
            suggested_score=job.suggested_score,
            suggested_reasoning=job.suggested_reasoning,
            final_score=job.final_score,
            override_reason=job.override_reason,
            overridden_by=job.overridden_by,
            attempt_count=job.attempt_count,
            last_error=job.last_error,
            scored_at=job.scored_at,
        )
