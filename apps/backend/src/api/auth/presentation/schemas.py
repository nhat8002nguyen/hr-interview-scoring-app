from pydantic import BaseModel

from iam import Role


class CredentialsBody(BaseModel):
    email: str
    password: str


class RefreshTokenBody(BaseModel):
    refresh_token: str


class SignOutBody(BaseModel):
    refresh_token: str | None = None


class HrUserResponse(BaseModel):
    id: int
    email: str
    role: Role


class AuthTokensResponse(BaseModel):
    user: HrUserResponse
    access_token: str
    refresh_token: str
