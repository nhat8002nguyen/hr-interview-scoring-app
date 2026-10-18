from iam.domain.entities import AccessScope
from iam.domain.exceptions import ForbiddenError


def ensure_resource_access(
    scope: AccessScope,
    *,
    owner_id: int,
    group_id: int | None,
    resource_name: str = "resource",
) -> None:
    if not scope.can_access(owner_id, group_id):
        raise ForbiddenError(f"You do not have permission to access this {resource_name}")


def ensure_group_assignment(scope: AccessScope, group_id: int | None) -> None:
    if not scope.can_assign_group(group_id):
        raise ForbiddenError("You cannot assign a resource to a group you do not belong to")
