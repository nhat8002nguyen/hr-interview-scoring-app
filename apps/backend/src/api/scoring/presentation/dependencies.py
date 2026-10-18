from typing import Annotated, cast

from fastapi import Depends, Request

from api.candidates.application.service import AnswersService
from api.catalog.application.service import CatalogService
from api.scoring.application.service import ScoringService


async def get_scoring_service(request: Request) -> ScoringService:
    return cast(ScoringService, request.app.state.scoring_service)


async def get_answers_service(request: Request) -> AnswersService:
    return cast(AnswersService, request.app.state.answers_service)


async def get_catalog_service(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog_service)


ScoringServiceDep = Annotated[ScoringService, Depends(get_scoring_service)]
AnswersServiceDep = Annotated[AnswersService, Depends(get_answers_service)]
CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
