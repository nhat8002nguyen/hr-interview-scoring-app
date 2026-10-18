from iam.application.api_key import ApiKeyService
from iam.application.hashing import BcryptHashingService
from iam.application.jwt import JwtService, RefreshTokenClaims
from iam.application.policy import ensure_group_assignment, ensure_resource_access
from iam.config import JwtSettings
from iam.domain.entities import (
    AccessScope,
    ActiveUserData,
    AuthType,
    GeneratedApiKey,
    Role,
    StoredApiKey,
)
from iam.domain.exceptions import ForbiddenError, UnauthorizedError
from iam.domain.ports import (
    ApiKeyValidatorProtocol,
    HashingServiceProtocol,
    RefreshTokenStorageProtocol,
)
from iam.presentation.dependencies import (
    CurrentAccessScopeDep,
    CurrentUserDep,
    get_access_scope,
    get_current_user,
    require_auth,
    require_roles,
)
from iam.presentation.errors import register_iam_exception_handlers

__all__ = [
    "AccessScope",
    "ActiveUserData",
    "ApiKeyService",
    "ApiKeyValidatorProtocol",
    "AuthType",
    "BcryptHashingService",
    "CurrentAccessScopeDep",
    "CurrentUserDep",
    "ForbiddenError",
    "GeneratedApiKey",
    "HashingServiceProtocol",
    "JwtService",
    "JwtSettings",
    "RefreshTokenClaims",
    "RefreshTokenStorageProtocol",
    "Role",
    "StoredApiKey",
    "UnauthorizedError",
    "ensure_group_assignment",
    "ensure_resource_access",
    "get_access_scope",
    "get_current_user",
    "register_iam_exception_handlers",
    "require_auth",
    "require_roles",
]
