"""Anonymous per-page reader usage, independent of patient/case persistence."""
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base, UUIDPrimaryKeyMixin


class LabReaderEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'lab_reader_events'
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
