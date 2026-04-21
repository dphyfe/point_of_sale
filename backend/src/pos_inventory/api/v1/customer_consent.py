"""Stub router for customer consent — wired in US5 (P3)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/customers", tags=["customer-consent"])
