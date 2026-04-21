"""Stub router for customer transaction history — wired in US2 (P1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/customers", tags=["customer-history"])
