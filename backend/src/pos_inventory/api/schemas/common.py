"""Common Pydantic schemas: error envelope and shared aliases."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Money = Decimal
Quantity = Decimal


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class IdResponse(BaseModel):
    id: UUID


class PageMeta(BaseModel):
    total: int = 0
    limit: int = 50
    offset: int = 0


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class TimeRange(BaseModel):
    start: str = Field(..., description="ISO-8601 timestamp")
    end: str = Field(..., description="ISO-8601 timestamp")
