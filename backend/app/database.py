from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session
from app.config import get_settings

settings = get_settings()

# Async engine (FastAPI)
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine (Celery tasks)
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=5,
)

SyncSessionFactory = None  # lazily created


def _get_sync_session_factory():
    global SyncSessionFactory
    if SyncSessionFactory is None:
        from sqlalchemy.orm import sessionmaker
        SyncSessionFactory = sessionmaker(
            sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
    return SyncSessionFactory


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_db() -> Session:
    """同步数据库 session，供 Celery 任务使用。"""
    factory = _get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db():
    """Create all tables (for dev; use Alembic in production)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE problems ADD COLUMN IF NOT EXISTS ocr_result JSONB"
        ))
