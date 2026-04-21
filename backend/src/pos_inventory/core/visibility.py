"""Visibility scope (R9, FR-008).

JWT may include `visibility_scope` ('all' | 'site') and `assigned_site_ids` (uuid[]).
For the customer-view feature this is JWT-only: there is no per-tenant override.

Helpers translate scope into a SQL filter clause for the customer-history
read path (which joins to `inv.location`/`inv.site`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from fastapi import Depends, Request

from pos_inventory.core.auth import Principal, get_principal


@dataclass(frozen=True)
class VisibilityScope:
    scope: str  # 'all' | 'site'
    site_ids: frozenset[UUID]

    @property
    def is_all(self) -> bool:
        return self.scope == "all"


def visibility_scope(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> VisibilityScope:
    """Resolve the request's visibility scope from JWT claims (or dev headers).

    Dev/test bypass: `X-Dev-Visibility-Scope` and `X-Dev-Site-Ids`
    (comma-separated UUIDs) when `auth_bypass=true`.
    """
    raw_scope: str | None = None
    raw_sites: Iterable[str] = ()

    # JWT path: when present on the principal/request, prefer those claims.
    claims = getattr(request.state, "jwt_claims", None)
    if isinstance(claims, dict):
        raw_scope = claims.get("visibility_scope")
        raw_sites = claims.get("assigned_site_ids") or ()

    # Dev bypass — same convention as core.auth
    if raw_scope is None:
        header_scope = request.headers.get("X-Dev-Visibility-Scope")
        if header_scope:
            raw_scope = header_scope
            raw_sites = [s for s in request.headers.get("X-Dev-Site-Ids", "").split(",") if s]

    scope = raw_scope or "all"
    site_ids = frozenset(UUID(s.strip()) for s in raw_sites if s and str(s).strip())

    # Admin always has 'all' visibility
    if "Admin" in principal.roles:
        scope = "all"

    return VisibilityScope(scope=scope, site_ids=site_ids)
