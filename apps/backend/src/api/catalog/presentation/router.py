from fastapi import APIRouter, Depends

from api.catalog.application.service import RoleWithCount
from api.catalog.presentation.dependencies import CatalogServiceDep
from api.catalog.presentation.schemas import RoleResponse
from iam import AuthType, CurrentUserDep, Role, require_auth, require_roles

catalog_router = APIRouter(prefix="/hr", tags=["hr"])

_require_hr = [
    Depends(require_auth(AuthType.JWT)),
    Depends(require_roles(Role.HR)),
]


@catalog_router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=_require_hr,
)
async def list_roles(user: CurrentUserDep, service: CatalogServiceDep) -> list[RoleResponse]:
    roles = await service.list_roles(user.sub)
    return [_to_response(role) for role in roles]


def _to_response(role: RoleWithCount) -> RoleResponse:
    return RoleResponse(
        id=role.role.id,
        name=role.role.name,
        candidate_count=role.candidate_count,
    )
