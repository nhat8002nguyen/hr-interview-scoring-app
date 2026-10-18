from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import JSONResponse

from api.candidates.application.service import SubmitResult
from api.candidates.domain.entities import Answer
from api.candidates.presentation.dependencies import (
    AnswersServiceDep,
    CandidateDep,
    CatalogServiceDep,
)
from api.candidates.presentation.errors import CandidateValidationError
from api.candidates.presentation.schemas import (
    InterviewAnswer,
    InterviewCandidate,
    InterviewQuestion,
    InterviewResponse,
    Progress,
    SubmitResponse,
    SubmittedAnswer,
    TextAnswerBody,
)

candidate_router = APIRouter(prefix="/candidate", tags=["candidate"])


def _interview_answer(answer: Answer | None) -> InterviewAnswer | None:
    if answer is None:
        return None
    return InterviewAnswer(
        answer_type=answer.answer_type,
        text=answer.text,
        version=answer.version,
        submitted_at=answer.submitted_at,
    )


def _submitted_answer(answer: Answer) -> SubmittedAnswer:
    return SubmittedAnswer(
        answer_type=answer.answer_type,
        version=answer.version,
        submitted_at=answer.submitted_at,
    )


def _submit_response(result: SubmitResult) -> SubmitResponse:
    return SubmitResponse(
        status=result.status,
        unchanged=result.unchanged,
        answer=_submitted_answer(result.answer),
    )


@candidate_router.get("/interview", response_model=InterviewResponse)
async def get_interview(
    candidate: CandidateDep,
    answers: AnswersServiceDep,
    catalog: CatalogServiceDep,
) -> InterviewResponse:
    role = await catalog.get_role(candidate.role_id)
    questions = await catalog.list_questions()
    active = await answers.list_for_candidate(candidate.id)
    answers_by_question = {answer.question_id: answer for answer in active}
    return InterviewResponse(
        candidate=InterviewCandidate(
            id=candidate.id,
            name=candidate.name,
            role=role.name,
        ),
        questions=[
            InterviewQuestion(
                id=question.id,
                code=question.code,
                sort_order=question.sort_order,
                prompt=question.prompt,
                answer=_interview_answer(answers_by_question.get(question.id)),
            )
            for question in questions
        ],
        progress=Progress(answered=len(active), total=len(questions)),
    )


@candidate_router.post(
    "/interview/answers/{question_id}",
    response_model=SubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_text(
    question_id: int,
    body: TextAnswerBody,
    candidate: CandidateDep,
    answers: AnswersServiceDep,
) -> SubmitResponse | JSONResponse:
    if not body.text.strip():
        raise CandidateValidationError("text must not be empty")
    result = await answers.submit_text(candidate.id, question_id, body.text)
    return _submit_or_unchanged(result)


@candidate_router.post(
    "/interview/answers/{question_id}/audio",
    response_model=SubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_audio(
    question_id: int,
    candidate: CandidateDep,
    answers: AnswersServiceDep,
    file: Annotated[UploadFile, File()],
) -> SubmitResponse | JSONResponse:
    data = await file.read()
    if not data:
        raise CandidateValidationError("audio file must not be empty")
    result = await answers.submit_audio(
        candidate.id,
        question_id,
        data,
        file.filename or "audio.m4a",
    )
    return _submit_or_unchanged(result)


def _submit_or_unchanged(result: SubmitResult) -> SubmitResponse | JSONResponse:
    response = _submit_response(result)
    if result.unchanged:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response.model_dump(mode="json"),
        )
    return response
