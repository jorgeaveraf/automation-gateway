from uuid import UUID

from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool


class ConnectionEnvironment(str, Enum):
    PROD = "prod"
    SANDBOX = "sandbox"


class ConnectionStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="qbo", min_length=1, max_length=32)
    environment: ConnectionEnvironment
    is_connected: StrictBool
    checked_at: AwareDatetime
    correlation_id: UUID


class ConnectionStatusResponse(ConnectionStatusRequest):
    client_id: UUID

    @classmethod
    def from_request(
        cls,
        client_id: UUID,
        request: ConnectionStatusRequest,
    ) -> "ConnectionStatusResponse":
        return cls(client_id=client_id, **request.model_dump())
