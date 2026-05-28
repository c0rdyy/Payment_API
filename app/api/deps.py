from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.ports.payment_gateway import PaymentGateway
from app.application.ports.unit_of_work import UnitOfWork
from app.application.services.create_payment import CreatePayment
from app.application.services.idempotency_service import IdempotencyService
from app.core.config import Settings, get_settings
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
SessionFactory = async_sessionmaker[AsyncSession]
MAX_IDEMPOTENCY_KEY_LENGTH = 255


def get_app_settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_engine(request: Request, settings: SettingsDep) -> AsyncEngine:
    engine: AsyncEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        engine = create_engine(settings)
        request.app.state.engine = engine
    return engine


def get_session_factory(
    request: Request,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> SessionFactory:
    factory: SessionFactory | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        factory = create_session_factory(engine)
        request.app.state.session_factory = factory
    return factory


def get_uow_factory(
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> UnitOfWorkFactory:
    def _make() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(factory)

    return _make


def get_payment_gateway(request: Request) -> PaymentGateway:
    gateway: PaymentGateway | None = getattr(request.app.state, "payment_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payment gateway is not configured",
        )
    return gateway


def get_idempotency_service(
    settings: SettingsDep,
    uow_factory: Annotated[UnitOfWorkFactory, Depends(get_uow_factory)],
) -> IdempotencyService:
    return IdempotencyService(
        uow_factory,
        ttl=timedelta(hours=settings.idempotency_key_ttl_hours),
    )


def get_create_payment(
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> CreatePayment:
    return CreatePayment(gateway)


def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Idempotency-Key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters",
        )
    return idempotency_key


def require_api_key(
    settings: SettingsDep,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if api_key != settings.app_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )
