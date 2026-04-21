"""Stub router for customer messages — wired in US4 (P2)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/customers", tags=["customer-messages"])
