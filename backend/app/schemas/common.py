from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // max(1, self.page_size)))


class Message(BaseModel):
    message: str


class IDResponse(BaseModel):
    id: uuid.UUID


class ErrorResponse(BaseModel):
    error: str
    code: str
    details: dict = Field(default_factory=dict)


class Timestamped(ORMModel):
    created_at: datetime
    updated_at: datetime
