from fastapi import APIRouter, status
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", status_code=status.HTTP_200_OK, response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/ready", status_code=status.HTTP_200_OK, response_model=HealthResponse)
async def ready() -> HealthResponse:
    return HealthResponse(status="ready", version=__version__)
