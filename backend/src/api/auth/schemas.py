"""Login request/response Pydantic modelleri."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds.")


class MeResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None = None
    is_active: bool
    is_superuser: bool


class LdapMappingCreate(BaseModel):
    org_id: str
    group_dn: str = Field(min_length=3, max_length=512)
    role: str = Field(min_length=1, max_length=64,
                      description="Rol adı (admin/editor/viewer/redteam_operator).")
    namespace_id: str | None = None


class LdapMappingItem(BaseModel):
    id: str
    org_id: str
    group_dn: str
    role: str
    role_id: str
    namespace_id: str | None = None
    created_at: str


__all__ = [
    "LoginRequest",
    "RefreshRequest",
    "TokenResponse",
    "MeResponse",
    "LdapMappingCreate",
    "LdapMappingItem",
]
