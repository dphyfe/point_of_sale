"""Consent schemas (FR-030..FR-032)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

Channel = Literal["email", "sms"]
Purpose = Literal["transactional", "marketing"]
EventKind = Literal["opted_in", "opted_out"]
StateValue = Literal["opted_in", "opted_out", "unset"]
Source = Literal["pos", "online_portal", "support", "provider_unsubscribe", "import"]


class ConsentEventCreate(BaseModel):
    channel: Channel
    purpose: Purpose
    event_kind: EventKind
    source: Source = "pos"
    note: str | None = None


class ConsentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    channel: Channel
    purpose: Purpose
    event_kind: EventKind
    source: Source
    actor_user_id: UUID | None = None
    occurred_at: datetime
    note: str | None = None


class ConsentStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    channel: Channel
    purpose: Purpose
    state: StateValue
    updated_at: datetime
