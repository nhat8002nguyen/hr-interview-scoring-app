from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: int
    name: str
    candidate_count: int
