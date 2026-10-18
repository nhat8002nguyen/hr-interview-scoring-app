from typing import Literal

from fastapi import APIRouter, Depends

from api.candidates.presentation.schemas import AnswerDetailResponse, ScoringDetail
from api.scoring.domain.entities import ScoringJob, ScoringJobSummary
from api.scoring.presentation.dependencies import (
    AnswersServiceDep,
    CatalogServiceDep,
    ScoringServiceDep,
)
from api.scoring.presentation.schemas import (
    ScoreOverrideBody,
    ScoringJobResponse,
    ScoringJobSummaryResponse,
)
from iam import AuthType, CurrentUserDep, Role, require_auth, require_roles

scoring_router = APIRouter(prefix="/hr", tags=["hr"])

_require_hr = [
    Depends(require_auth(AuthType.JWT)),
    Depends(require_roles(Role.HR)),
]

_ScoringStatus = Literal["queued", "scored", "failed", "needs_a_person"]


def _scoring_detail(job: ScoringJob) -> ScoringDetail:
    return ScoringDetail(
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


def _job_response(job: ScoringJob) -> ScoringJobResponse:
    return ScoringJobResponse(
        id=job.id,
        answer_id=job.answer_id,
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


def _summary_response(summary: ScoringJobSummary) -> ScoringJobSummaryResponse:
    return ScoringJobSummaryResponse(
        id=summary.id,
        answer_id=summary.answer_id,
        candidate_id=summary.candidate_id,
        candidate_name=summary.candidate_name,
        question_code=summary.question_code,
        status=summary.status,
        attempt_count=summary.attempt_count,
        last_error=summary.last_error,
        created_at=summary.created_at,
    )


@scoring_router.patch(
    "/answers/{answer_id}/score",
    response_model=AnswerDetailResponse,
    dependencies=_require_hr,
)
async def override_answer_score(
    answer_id: int,
    body: ScoreOverrideBody,
    user: CurrentUserDep,
    scoring: ScoringServiceDep,
    answers: AnswersServiceDep,
    catalog: CatalogServiceDep,
) -> AnswerDetailResponse:
    job = await scoring.override_score(
        answer_id,
        final_score=body.final_score,
        override_reason=body.override_reason,
        overridden_by=user.sub,
    )
    answer = await answers.get(answer_id)
    question = await catalog.get_question(answer.question_id)
    return AnswerDetailResponse(
        id=answer.id,
        candidate_id=answer.candidate_id,
        question_id=answer.question_id,
        question_code=question.code,
        question_prompt=question.prompt,
        grading_guide=question.grading_guide,
        answer_type=answer.answer_type,
        text=answer.text,
        version=answer.version,
        submitted_at=answer.submitted_at,
        scoring=_scoring_detail(job),
    )


@scoring_router.get(
    "/scoring-jobs",
    response_model=list[ScoringJobSummaryResponse],
    dependencies=_require_hr,
)
async def list_scoring_jobs(
    scoring: ScoringServiceDep,
    status: _ScoringStatus | None = None,
) -> list[ScoringJobSummaryResponse]:
    jobs = await scoring.list_jobs(status)
    return [_summary_response(job) for job in jobs]


@scoring_router.post(
    "/scoring-jobs/{job_id}/retry",
    response_model=ScoringJobResponse,
    dependencies=_require_hr,
)
async def retry_scoring_job(
    job_id: int,
    scoring: ScoringServiceDep,
) -> ScoringJobResponse:
    job = await scoring.retry(job_id)
    return _job_response(job)
