from typing import Annotated, cast

from fastapi import Depends, Request

from api.catalog.application.service import CatalogService


async def get_catalog_service(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog_service)


CatalogServiceDep = Annotated[
    CatalogService,
    Depends(get_catalog_service),
]
