import json
import time
from pathlib import Path

from sqlalchemy import Float, Index, Integer, String, Text, create_engine, event, select, delete
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    mint: Mapped[str] = mapped_column(String(64), default="")
    ts: Mapped[float] = mapped_column(Float)
    session: Mapped[str] = mapped_column(String(40), default="")
    payload: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        Index("ix_kind_ts", "kind", "ts"),
        Index("ix_mint_ts", "mint", "ts"),
        Index("ix_session_kind", "session", "kind"),
    )


class EventIdentity(Base):
    __tablename__ = "event_identities"
    event_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    ts: Mapped[float] = mapped_column(Float, index=True)


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def configure(dbapi, _):
            dbapi.execute("PRAGMA journal_mode=WAL")
            dbapi.execute("PRAGMA busy_timeout=5000")
            dbapi.execute("PRAGMA synchronous=NORMAL")
            dbapi.execute("PRAGMA foreign_keys=ON")

        # CLI/startup runs Alembic; tests may provision metadata directly.
        self.sessions = sessionmaker(self.engine)

    def reserve_event(self, event_id, ts):
        from sqlalchemy.dialects.sqlite import insert

        with self.sessions.begin() as db:
            result = db.execute(
                insert(EventIdentity).values(event_id=event_id, ts=ts).on_conflict_do_nothing()
            )
            return getattr(result, "rowcount", 0) == 1

    def add(self, kind, payload, mint="", session="", ts=None):
        with self.sessions.begin() as db:
            row = Record(
                kind=kind,
                mint=mint,
                session=session,
                ts=time.time() if ts is None else ts,
                payload=json.dumps(payload, separators=(",", ":"), allow_nan=False),
            )
            db.add(row)
            db.flush()
            return row.id

    def rows(self, kind, mint=None, session=None, limit=500, after=0):
        query = select(Record).where(Record.kind == kind, Record.id > after)
        if mint is not None:
            query = query.where(Record.mint == mint)
        if session is not None:
            query = query.where(Record.session == session)
        with self.sessions() as db:
            rows = db.scalars(query.order_by(Record.id.desc()).limit(min(limit, 10000))).all()
            return [
                {**json.loads(r.payload), "id": r.id, "ts": r.ts, "mint": r.mint, "session": r.session}
                for r in reversed(rows)
            ]

    def iterate(self, kind, session=None):
        cursor = 0
        while True:
            query = select(Record).where(Record.kind == kind, Record.id > cursor)
            if session is not None:
                query = query.where(Record.session == session)
            with self.sessions() as db:
                batch = db.scalars(query.order_by(Record.id).limit(500)).all()
                if not batch:
                    return
                result = [
                    {**json.loads(r.payload), "id": r.id, "ts": r.ts, "mint": r.mint, "session": r.session}
                    for r in batch
                ]
            for row in result:
                cursor = row["id"]
                yield row

    def size(self):
        return sum(p.stat().st_size for p in self.path.parent.glob(self.path.name + "*") if p.is_file())

    def retention(self, settings, now=None):
        now = time.time() if now is None else now
        groups = {
            "event": settings.raw_retention_hours * 3600,
            "snapshot": settings.snapshot_retention_days * 86400,
            "security": settings.snapshot_retention_days * 86400,
            "creator_profile": settings.snapshot_retention_days * 86400,
            "graduation": settings.snapshot_retention_days * 86400,
            "session": settings.outcome_retention_days * 86400,
            "session_context": settings.outcome_retention_days * 86400,
            "transition": settings.snapshot_retention_days * 86400,
            "signal": settings.outcome_retention_days * 86400,
            "outcome": settings.outcome_retention_days * 86400,
        }
        count = 0
        with self.sessions.begin() as db:
            db.execute(
                delete(EventIdentity).where(EventIdentity.ts < now - settings.raw_retention_hours * 3600)
            )
            for kind, seconds in groups.items():
                result = db.execute(delete(Record).where(Record.kind == kind, Record.ts < now - seconds))
                count += getattr(result, "rowcount", 0)
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        return count

    def optimize(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.exec_driver_sql("VACUUM")
            conn.exec_driver_sql("PRAGMA optimize")
