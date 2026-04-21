"""Stub router for customer addresses — wired in US3 (P1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/customers", tags=["customer-addresses"])
