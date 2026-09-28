"""Company schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: str | None = Field(default=None, max_length=400)
    industry: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=4000)
    logo_url: str | None = Field(default=None, max_length=400)
    location: str | None = Field(default=None, max_length=150)
    contact_email: EmailStr
    contact_name: str | None = Field(default=None, max_length=150)
    tiers: list[str] = Field(default_factory=list, max_length=10)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    website: str | None = Field(default=None, max_length=400)
    industry: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=4000)
    logo_url: str | None = Field(default=None, max_length=400)
    location: str | None = Field(default=None, max_length=150)
    contact_email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    tiers: list[str] | None = Field(default=None, max_length=10)
    reputation_score: float | None = Field(default=None, ge=0, le=5)
    is_active: bool | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    website: str | None = None
    industry: str | None = None
    about: str | None = None
    location: str | None = None
    contact_email: EmailStr
    contact_name: str | None = None
    tiers: list[str] = Field(default_factory=list)
    reputation_score: float | None = None
    is_active: bool
    created_at: datetime


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    industry: str | None = None
    location: str | None = None


class PaginatedCompanies(BaseModel):
    items: list[CompanyRead]
    total: int
    page: int
    limit: int