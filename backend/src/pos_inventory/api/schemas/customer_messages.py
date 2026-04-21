"""Customer messaging schemas (FR-024..FR-035)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["email", "sms"]
Purpose = Literal["transactional", "marketing"]
MessageStatus = Literal["queued", "sent", "delivered", "bounced", "failed", "retrying"]


class TemplateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    channel: Channel
    purpose: Purpose
    subject_template: str | None = None
    body_template: str
    enabled: bool = True


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    enabled: bool | None = None


class TemplateRead(TemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    template_code: str | None = None
    channel: Channel | None = None
    subject: str | None = None
    body: str | None = None
    related_transaction_id: UUID | None = None
    related_transaction_kind: str | None = None
    client_request_id: UUID | None = None
    merge_fields: dict[str, str] = Field(default_factory=dict)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    template_id: UUID | None = None
    channel: Channel
    purpose: Purpose
    to_address: str
    subject: str | None = None
    body: str
    status: MessageStatus
    related_transaction_id: UUID | None = None
    related_transaction_kind: str | None = None
    created_at: datetime
    updated_at: datetime
