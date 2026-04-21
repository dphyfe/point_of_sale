"""Stub router for message templates — wired in US5 (P3)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/message-templates", tags=["message-templates"])
