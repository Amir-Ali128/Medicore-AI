"""Opt-in analytics storage; never creates or changes patient records."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import text
from app.core.config import get_settings
from app.domain import consistency_config as cfg
from app.infrastructure.database.models.lab_reader_event import LabReaderEvent
from app.infrastructure.database.session import AsyncSessionFactory

async def ensure_lab_reader_events(engine):
    if not getattr(get_settings(), 'lab_cross_read_enabled', False): return
    async with engine.begin() as connection:
        await connection.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'), {'lock_id': cfg.READER_MIGRATION_LOCK})
        await connection.execute(text('''CREATE TABLE IF NOT EXISTS lab_reader_events (
            id UUID PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
        )'''))
        await connection.execute(text('CREATE INDEX IF NOT EXISTS ix_lab_reader_events_recorded_at ON lab_reader_events (recorded_at)'))


async def persist_reader_event(event):
    if not getattr(get_settings(), 'lab_cross_read_enabled', False): return
    async with AsyncSessionFactory() as session:
        session.add(LabReaderEvent(id=UUID(event['event_id']),recorded_at=datetime.fromisoformat(event['recorded_at']),
                                  payload={key:event.get(key) for key in cfg.READER_ANALYTICS_FIELDS}))
        await session.commit()
