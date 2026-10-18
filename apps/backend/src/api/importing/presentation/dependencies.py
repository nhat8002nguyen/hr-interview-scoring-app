from typing import Annotated, cast

from fastapi import Depends, Request

from api.importing.application.service import ImportService


async def get_import_service(request: Request) -> ImportService:
    return cast(ImportService, request.app.state.import_service)


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
