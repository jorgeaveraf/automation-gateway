from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from automation_gateway.api.dependencies import (
    get_connection_status_publisher,
    require_api_key,
)
from automation_gateway.application.ports import ConnectionStatusPublisher
from automation_gateway.application.publish_connection_status import PublishConnectionStatus
from automation_gateway.core.errors import (
    PublisherNotConfiguredError,
    PublisherTimeoutError,
    PublisherUnavailableError,
)
from automation_gateway.schemas.connection_status import (
    ConnectionStatusRequest,
    ConnectionStatusResponse,
)


router = APIRouter(
    prefix="/v1/connections",
    tags=["connection-status"],
    dependencies=[Depends(require_api_key)],
)


@router.put(
    "/{client_id}/status",
    response_model=ConnectionStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def publish_connection_status(
    client_id: UUID,
    request: ConnectionStatusRequest,
    publisher: ConnectionStatusPublisher = Depends(get_connection_status_publisher),
) -> ConnectionStatusResponse:
    use_case = PublishConnectionStatus(publisher)
    try:
        return await use_case.execute(client_id, request)
    except PublisherNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PublisherTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except PublisherUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
