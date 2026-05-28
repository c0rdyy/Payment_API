from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.infrastructure.db.models import Base


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        image="postgres:16-alpine",
        username="payments",
        password="payments",
        dbname="payments_test",
        driver="asyncpg",
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def _migrated_database(database_url: str) -> str:
    async def _setup() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_setup())
    return database_url


@pytest.fixture
async def db_session(_migrated_database: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_migrated_database)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE outbox_events, idempotency_keys, payment_attempts, payments "
                "RESTART IDENTITY CASCADE"
            )
        )

    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
async def session_factory(
    _migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_migrated_database)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE outbox_events, idempotency_keys, payment_attempts, payments "
                "RESTART IDENTITY CASCADE"
            )
        )

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def alembic_config(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def alembic_upgrade(cfg: AlembicConfig, revision: str = "head") -> None:
    command.upgrade(cfg, revision)


def alembic_downgrade(cfg: AlembicConfig, revision: str = "base") -> None:
    command.downgrade(cfg, revision)
