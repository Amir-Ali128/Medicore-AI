import asyncio
import importlib
import pkgutil

from app.infrastructure.database.base import Base
from app.infrastructure.database import session
import app.infrastructure.database.models as models_pkg


# Register all SQLAlchemy models into Base.metadata
for module in pkgutil.iter_modules(models_pkg.__path__):
    importlib.import_module(f"{models_pkg.__name__}.{module.name}")


engine = (
    getattr(session, "async_engine", None)
    or getattr(session, "engine", None)
)

if engine is None:
    raise RuntimeError("Could not find SQLAlchemy async engine in database session module.")


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database tables created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
