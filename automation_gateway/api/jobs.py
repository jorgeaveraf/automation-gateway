from fastapi import APIRouter, Depends, HTTPException, status

from automation_gateway.api.dependencies import get_job_queue, require_api_key
from automation_gateway.application.ports import JobQueue
from automation_gateway.core.errors import (
    JobQueueNotConfiguredError,
    JobQueueUnavailableError,
    UnsupportedJobKindError,
)
from automation_gateway.schemas.jobs import JobAcceptance, JobEnvelope


router = APIRouter(
    prefix="/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=JobAcceptance, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    job: JobEnvelope,
    queue: JobQueue = Depends(get_job_queue),
) -> JobAcceptance:
    try:
        is_new = await queue.enqueue(job)
    except JobQueueNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except JobQueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except UnsupportedJobKindError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return JobAcceptance(event_id=job.event_id, duplicate=not is_new)
