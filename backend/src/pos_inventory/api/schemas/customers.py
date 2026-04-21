"""Customer-view Pydantic v2 schemas (FR-001..FR-018)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ContactType = Literal["individual", "company"]
PreferredChannel = Literal["email", "sms", "none"]
CustomerState = Literal["active", "inactive", "merged", "anonymized"]
AddressKind = Literal["billing", "shipping", "service"]


class CustomerBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_type: ContactType = "individual"
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    primary_phone: str | None = None
    secondary_phone: str | None = None
    email: EmailStr | None = None
    preferred_channel: PreferredChannel = "email"
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    external_loyalty_id: str | None = None
    external_crm_id: str | None = None


class CustomerCreate(CustomerBase):
    client_request_id: UUID | None = None
    tax_id: str | None = None
    date_of_birth: date | None = None


class CustomerUpdate(CustomerBase):
    tax_id: str | None = None
    date_of_birth: date | None = None


class CustomerRead(CustomerBase):
    id: UUID
    state: CustomerState
    version: int
    display_name: str = ""
    merged_into: UUID | None = None
    tax_id_masked: str | None = None
    date_of_birth: date | None = None
    last_purchase_at: datetime | None = None
    last_store_visited: str | None = None
    lifetime_spend: Decimal = Decimal("0")
    visit_count: int = 0
    average_order_value: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime


class CustomerSummary(BaseModel):
    """Compact summary used in search results (FR-001..FR-005)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_type: ContactType
    display_name: str
    email: EmailStr | None = None
    primary_phone: str | None = None
    state: CustomerState
    tags: list[str] = Field(default_factory=list)


class CustomerSearchResponse(BaseModel):
    items: list[CustomerSummary]
    total: int
    limit: int
    offset: int


class CustomerAddressBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: AddressKind
    is_default_for_kind: bool = False
    line1: str
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str = Field(min_length=2, max_length=2)


class CustomerAddressCreate(CustomerAddressBase):
    pass


class CustomerAddressRead(CustomerAddressBase):
    id: UUID
    customer_id: UUID


class MergeRequest(BaseModel):
    survivor_id: UUID
    merged_away_id: UUID
    summary: str | None = None


class DeactivateRequest(BaseModel):
    reason: str | None = None
