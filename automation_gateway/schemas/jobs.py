from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    kind: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any]


class JobAcceptance(BaseModel):
    event_id: UUID
    accepted: bool = True
    duplicate: bool
