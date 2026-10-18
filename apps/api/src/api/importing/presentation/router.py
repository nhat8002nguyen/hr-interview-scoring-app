from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.exceptions import HTTPException

from api.importing.application.service import ImportSummary
from api.importing.presentation.dependencies import ImportServiceDep
from api.importing.presentation.schemas import ImportSummaryResponse
from iam import AuthType, Role, require_auth, require_roles

import_router = APIRouter(prefix="/hr", tags=["hr"])

MAX_IMPORT_BYTES = 25 * 1024 * 1024

_require_hr = [
    Depends(require_auth(AuthType.JWT)),
    Depends(require_roles(Role.HR)),
]


@import_router.post(
    "/import",
    response_model=ImportSummaryResponse,
    dependencies=_require_hr,
)
async def import_pack(
    importer: ImportServiceDep,
    file: Annotated[UploadFile, File()],
) -> ImportSummaryResponse:
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="import pack exceeds the maximum size",
        )
    summary = await importer.import_zip(data)
    return _to_response(summary)


def _to_response(summary: ImportSummary) -> ImportSummaryResponse:
    return ImportSummaryResponse(
        roles_created=summary.roles_created,
        questions_created=summary.questions_created,
        candidates_created=summary.candidates_created,
        answers_imported=summary.answers_imported,
        scoring_jobs_queued=summary.scoring_jobs_queued,
        audio_answers_needing_person=summary.audio_answers_needing_person,
    )
