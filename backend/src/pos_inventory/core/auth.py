"""JWT verification + role gating.

Canonical roles per FR-036 (001) + 002 customer-view extension:
Cashier, Receiver, Inventory Clerk, Store Manager, Purchasing, Admin,
Customer Service, Marketing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from pos_inventory.core.config import get_settings
from pos_inventory.core.errors import RoleForbidden

CANONICAL_ROLES = {
    "Cashier",
    "Receiver",
    "Inventory Clerk",
    "Store Manager",
    "Purchasing",
    "Admin",
    "Customer Service",
    "Marketing",
}

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    roles: frozenset[str]

    def has_any(self, roles: Iterable[str]) -> bool:
        wanted = set(roles)
        if not wanted:
            return True
        return bool(self.roles & wanted) or "Admin" in self.roles


def _decode(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            options={"verify_aud": settings.jwt_audience is not None},
        )
    except JWTError as e:  # pragma: no cover - exercised via integration
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from e


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve the request principal from the bearer JWT.

    Dev/test convenience: when `auth_bypass=true`, accept `X-Dev-Tenant`,
    `X-Dev-User`, and `X-Dev-Roles` headers.
    """
    settings = get_settings()
    if settings.auth_bypass:
        tid = request.headers.get("X-Dev-Tenant")
        uid = request.headers.get("X-Dev-User")
        roles = request.headers.get("X-Dev-Roles", "")
        if tid and uid:
            return Principal(
                user_id=UUID(uid),
                tenant_id=UUID(tid),
                roles=frozenset(r.strip() for r in roles.split(",") if r.strip()),
            )
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_token")
    claims = _decode(creds.credentials)
    try:
        return Principal(
            user_id=UUID(claims["sub"]),
            tenant_id=UUID(claims["tenant_id"]),
            roles=frozenset(claims.get("roles", [])),
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_claims") from e


def requires_role(*roles: str):
    """FastAPI dependency factory that enforces the principal has any of `roles`."""
    unknown = set(roles) - CANONICAL_ROLES
    assert not unknown, f"Non-canonical role(s) requested: {unknown}"

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_any(roles):
            raise RoleForbidden(f"requires one of {sorted(roles)}")
        return principal

    return _dep
