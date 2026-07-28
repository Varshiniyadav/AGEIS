"""
database.py

Handles all database interactions for WBGT readings.
Supports SQLite (default) and PostgreSQL via SQLAlchemy.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------

def _build_engine():
    engine_type = os.getenv("DB_ENGINE", "sqlite").lower()

    if engine_type == "sqlite":
        path = os.getenv("SQLITE_PATH", "./wbgt_monitor.db")
        return create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )

    # PostgreSQL
    host   = os.getenv("DB_HOST",     "localhost")
    port   = os.getenv("DB_PORT",     "5432")
    name   = os.getenv("DB_NAME",     "wbgt")
    user   = os.getenv("DB_USER",     "postgres")
    passwd = os.getenv("DB_PASSWORD", "")
    return create_engine(
        f"postgresql+psycopg2://{user}:{passwd}@{host}:{port}/{name}"
    )


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class WbgtReading(Base):
    __tablename__ = "wbgt_readings"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    zone_id          = Column(String(64),  nullable=False, index=True)
    timestamp        = Column(String(64),  nullable=False)
    location_type    = Column(String(64),  nullable=True)
    is_outdoor       = Column(Boolean,     nullable=True)
    ta               = Column(Float,       nullable=True)
    rh               = Column(Float,       nullable=True)
    tg               = Column(Float,       nullable=True)
    tnwb             = Column(Float,       nullable=True)
    wbgt             = Column(Float,       nullable=True)
    risk_level       = Column(String(16),  nullable=True)
    data_quality_json = Column(Text,       nullable=True)
    created_at       = Column(DateTime,    default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Module-level singletons (initialised lazily)
# ---------------------------------------------------------------------------

_engine        = None
_SessionLocal  = None


def _get_session() -> Session:
    global _engine, _SessionLocal
    if _engine is None:
        _engine       = _build_engine()
        _SessionLocal = sessionmaker(bind=_engine)
        Base.metadata.create_all(_engine)
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Ensure tables exist. Safe to call multiple times."""
    _get_session().close()


def insert_reading(data: dict) -> int:
    """
    Insert a WBGT reading row.

    Expected keys (all optional except zone_id / timestamp):
        zone_id, timestamp, location_type, is_outdoor,
        ta, rh, tg, tnwb, wbgt, risk_level, data_quality (dict)
    Returns the new row id.
    """
    with _get_session() as session:
        row = WbgtReading(
            zone_id           = data.get("zone_id"),
            timestamp         = str(data.get("timestamp", "")),
            location_type     = data.get("location_type"),
            is_outdoor        = data.get("is_outdoor"),
            ta                = data.get("ta"),
            rh                = data.get("rh"),
            tg                = data.get("tg"),
            tnwb              = data.get("tnwb"),
            wbgt              = data.get("wbgt"),
            risk_level        = data.get("risk_level"),
            data_quality_json = json.dumps(data.get("data_quality", {})),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def get_readings(
    zone_id: str = None,
    start: datetime = None,
    end: datetime   = None,
) -> list[dict]:
    """
    Retrieve wbgt_readings rows, optionally filtered by zone_id and/or
    created_at time range.

    Returns a list of dicts.
    """
    with _get_session() as session:
        query = session.query(WbgtReading)
        if zone_id:
            query = query.filter(WbgtReading.zone_id == zone_id)
        if start:
            query = query.filter(WbgtReading.created_at >= start)
        if end:
            query = query.filter(WbgtReading.created_at <= end)

        rows = query.all()

    result = []
    for row in rows:
        result.append({
            "id":           row.id,
            "zone_id":      row.zone_id,
            "timestamp":    row.timestamp,
            "location_type": row.location_type,
            "is_outdoor":   row.is_outdoor,
            "ta":           row.ta,
            "rh":           row.rh,
            "tg":           row.tg,
            "tnwb":         row.tnwb,
            "wbgt":         row.wbgt,
            "risk_level":   row.risk_level,
            "data_quality": json.loads(row.data_quality_json or "{}"),
            "created_at":   row.created_at.isoformat() if row.created_at else None,
        })
    return result
