from fastapi import APIRouter, Depends, Response, status

from api.candidates.application.ports import ScoringSnapshot
from api.candidates.domain.entities import Answer
from api.candidates.presentation.dependencies import (
    AnswersServiceDep,
    CandidatesServiceDep,
    CatalogServiceDep,
    ScoringReaderDep,
    SettingsDep,
)
from api.candidates.presentation.schemas import (
    AnswerDetailResponse,
    CandidateAnswerDetail,
    CandidateAnswerSummary,
    CandidateDetailResponse,
    CandidateListItem,
    CreateCandidateBody,
    CreateCandidateResponse,
    Progress,
    ScoringDetail,
    ScoringSummary,
)
from api.config import Settings
from iam import AuthType, CurrentUserDep, Role, require_auth, require_roles

hr_router = APIRouter(prefix="/hr", tags=["hr"])

_require_hr = [
    Depends(require_auth(AuthType.JWT)),
    Depends(require_roles(Role.HR)),
]


def _interview_link(settings: Settings, token: str) -> str:
    return f"{settings.candidate_web_origin}/interview/{token}"


def _progress(answers: list[Answer], total: int) -> Progress:
    return Progress(answered=len(answers), total=total)


def _scoring_summary(snapshot: ScoringSnapshot | None) -> ScoringSummary:
    if snapshot is None:
        return ScoringSummary(
            status="queued",
            suggested_score=None,
            final_score=None,
            override_reason=None,
        )
    return ScoringSummary(
        status=snapshot.status,
        suggested_score=snapshot.suggested_score,
        final_score=snapshot.final_score,
        override_reason=snapshot.override_reason,
    )


def _scoring_detail(snapshot: ScoringSnapshot | None) -> ScoringDetail:
    if snapshot is None:
        return ScoringDetail(
            status="queued",
            suggested_score=None,
            suggested_reasoning=None,
            final_score=None,
            override_reason=None,
            overridden_by=None,
            attempt_count=0,
            last_error=None,
            scored_at=None,
        )
    return ScoringDetail(
        status=snapshot.status,
        suggested_score=snapshot.suggested_score,
        suggested_reasoning=snapshot.suggested_reasoning,
        final_score=snapshot.final_score,
        override_reason=snapshot.override_reason,
        overridden_by=snapshot.overridden_by,
        attempt_count=snapshot.attempt_count,
        last_error=snapshot.last_error,
        scored_at=snapshot.scored_at,
    )


@hr_router.get(
    "/roles/{role_id}/candidates",
    response_model=list[CandidateListItem],
    dependencies=_require_hr,
)
async def list_candidates_for_role(
    role_id: int,
    user: CurrentUserDep,
    candidates: CandidatesServiceDep,
    answers: AnswersServiceDep,
    catalog: CatalogServiceDep,
    scoring: ScoringReaderDep,
) -> list[CandidateListItem]:
    questions = await catalog.list_questions()
    codes = {question.id: question.code for question in questions}
    total = len(questions)
    items: list[CandidateListItem] = []
    for candidate in await candidates.list_candidates_for_role(role_id, owner_id=user.sub):
        candidate_answers = await answers.list_for_candidate(candidate.id)
        answer_items: list[CandidateAnswerSummary] = []
        for answer in candidate_answers:
            snapshot = await scoring.get_snapshot(answer.id)
            answer_items.append(
                CandidateAnswerSummary(
                    id=answer.id,
                    question_id=answer.question_id,
                    question_code=codes.get(answer.question_id, ""),
                    answer_type=answer.answer_type,
                    version=answer.version,
                    scoring=_scoring_summary(snapshot),
                )
            )
        items.append(
            CandidateListItem(
                id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                answer_progress=_progress(candidate_answers, total),
                answers=answer_items,
            )
        )
    return items


@hr_router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateDetailResponse,
    dependencies=_require_hr,
)
async def get_candidate_detail(
    candidate_id: int,
    user: CurrentUserDep,
    candidates: CandidatesServiceDep,
    answers: AnswersServiceDep,
    catalog: CatalogServiceDep,
    scoring: ScoringReaderDep,
    settings: SettingsDep,
) -> CandidateDetailResponse:
    candidate = await candidates.get_owned_candidate(candidate_id, user.sub)
    questions = await catalog.list_questions()
    codes = {question.id: question.code for question in questions}
    total = len(questions)
    candidate_answers = await answers.list_for_candidate(candidate.id)
    answer_items: list[CandidateAnswerDetail] = []
    for answer in candidate_answers:
        snapshot = await scoring.get_snapshot(answer.id)
        answer_items.append(
            CandidateAnswerDetail(
                id=answer.id,
                question_id=answer.question_id,
                question_code=codes.get(answer.question_id, ""),
                answer_type=answer.answer_type,
                version=answer.version,
                scoring=_scoring_detail(snapshot),
            )
        )
    return CandidateDetailResponse(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        role_id=candidate.role_id,
        session_token=candidate.session_token,
        interview_link=_interview_link(settings, candidate.session_token),
        answer_progress=_progress(candidate_answers, total),
        answers=answer_items,
    )


@hr_router.post(
    "/candidates",
    response_model=CreateCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_require_hr,
)
async def create_candidate(
    body: CreateCandidateBody,
    user: CurrentUserDep,
    candidates: CandidatesServiceDep,
    settings: SettingsDep,
) -> CreateCandidateResponse:
    candidate = await candidates.create_candidate(
        name=body.name,
        email=body.email,
        role_id=body.role_id,
        owner_id=user.sub,
    )
    return CreateCandidateResponse(
        id=candidate.id,
        name=candidate.name or "",
        email=candidate.email,
        role_id=candidate.role_id,
        session_token=candidate.session_token,
        interview_link=_interview_link(settings, candidate.session_token),
    )


@hr_router.get(
    "/answers/{answer_id}",
    response_model=AnswerDetailResponse,
    dependencies=_require_hr,
)
async def get_answer_detail(
    answer_id: int,
    answers: AnswersServiceDep,
    catalog: CatalogServiceDep,
    scoring: ScoringReaderDep,
) -> AnswerDetailResponse:
    answer = await answers.get(answer_id)
    question = await catalog.get_question(answer.question_id)
    snapshot = await scoring.get_snapshot(answer.id)
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
        scoring=_scoring_detail(snapshot),
    )


@hr_router.get(
    "/answers/{answer_id}/audio",
    dependencies=_require_hr,
)
async def get_answer_audio(
    answer_id: int,
    answers: AnswersServiceDep,
) -> Response:
    data, media_type = await answers.read_audio(answer_id)
    return Response(content=data, media_type=media_type)
