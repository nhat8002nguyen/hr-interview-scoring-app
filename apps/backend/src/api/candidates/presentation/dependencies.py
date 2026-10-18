from typing import Annotated, cast

from fastapi import Depends, Request

from api.candidates.application.ports import ScoringReader
from api.candidates.application.service import AnswersService, CandidatesService
from api.candidates.domain.entities import Candidate
from api.catalog.application.service import CatalogService
from api.config import Settings
from iam import UnauthorizedError


async def get_candidates_service(request: Request) -> CandidatesService:
    return cast(CandidatesService, request.app.state.candidates_service)


async def get_answers_service(request: Request) -> AnswersService:
    return cast(AnswersService, request.app.state.answers_service)


async def get_catalog_service(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog_service)


async def get_scoring_reader(request: Request) -> ScoringReader:
    return cast(ScoringReader, request.app.state.scoring_reader)


async def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def require_candidate(request: Request) -> Candidate:
    token = request.headers.get("x-candidate-token")
    if not token:
        raise UnauthorizedError("Missing X-Candidate-Token header")
    candidates_service = cast(CandidatesService, request.app.state.candidates_service)
    candidate = await candidates_service.get_by_session_token(token)
    if candidate is None:
        raise UnauthorizedError("Invalid candidate token")
    return candidate


CandidatesServiceDep = Annotated[CandidatesService, Depends(get_candidates_service)]
AnswersServiceDep = Annotated[AnswersService, Depends(get_answers_service)]
CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
ScoringReaderDep = Annotated[ScoringReader, Depends(get_scoring_reader)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CandidateDep = Annotated[Candidate, Depends(require_candidate)]
