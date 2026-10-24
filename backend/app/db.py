import json
import time
import hashlib
import threading
from contextlib import nullcontext
from collections import OrderedDict
from pathlib import Path
from typing import Any

from sqlalchemy import Float, Index, Integer, String, Text, create_engine, event, select, delete, text, inspect, insert
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


class ManualPositionRow(Base):
    __tablename__ = "manual_positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(10), index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (Index("ix_manual_recent", "mode", "status", "updated_at"),)
    payload: Mapped[str] = mapped_column(Text)


class OpportunityPendingRow(Base):
    __tablename__ = "opportunity_pending"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class EvidenceContext(Base):
    __tablename__ = "evidence_contexts"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class EvidenceRun(Base):
    __tablename__ = "evidence_runs"
    session: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


# Parameterized, cacheable statements; same unique constraints and commit boundaries.
IDENTITY_INSERT = text("INSERT INTO event_identities (event_id, ts) "
                       "VALUES (:event_id, :ts) ON CONFLICT DO NOTHING")
RAW_EVENT_INSERT = insert(Record)


class StorageBudgetError(RuntimeError):
    """Essential evidence cannot be written safely; observation must stop."""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.record_observer: Any = None
        self._proof_lock = threading.Lock()
        self._write_proofs = {f"{kind}_{status}": 0 for kind in ("identity", "event")
                              for status in ("verified", "absent", "uncertain")}
        self.budget = 0
        self.page_size = 0
        self.context_cache: OrderedDict[str, None] = OrderedDict()
        self.storage_audit: dict[str, Any] = dict(raw_omitted=0, raw_reclaimed=0,
                                                raw_first_ts=None, raw_last_ts=None)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def configure(dbapi, _):
            dbapi.execute("PRAGMA journal_mode=WAL")
            dbapi.execute("PRAGMA busy_timeout=5000")
            dbapi.execute("PRAGMA synchronous=NORMAL")
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA wal_autocheckpoint=32")
            if self.budget:
                page_size = dbapi.execute("PRAGMA page_size").fetchone()[0]
                dbapi.execute(f"PRAGMA max_page_count={int(self.budget * .90) // page_size}")

        # CLI/startup runs Alembic; tests may provision metadata directly.
        self.sessions = sessionmaker(self.engine)

    def configure_budget(self, megabytes):
        # Leave headroom for WAL, SHM and the final operational receipt. Never raise the ceiling.
        self.budget = int(megabytes * 1048576)
        with self.sessions() as session:
            receipt = session.get(EvidenceRun, "storage")
            if receipt:
                self.storage_audit.update(json.loads(receipt.payload))
        with self.engine.connect() as db:
            page: int = db.exec_driver_sql("PRAGMA page_size").scalar_one()
            self.page_size = page
            limit = int(self.budget * .90) // page
            actual: int = db.exec_driver_sql(f"PRAGMA max_page_count={limit}").scalar_one()
            if actual > limit:
                raise StorageBudgetError("Existing database exceeds the evidence page budget")

    def context_reference(self, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        if digest not in self.context_cache:
            self.writable()
            from sqlalchemy.dialects.sqlite import insert

            with self.sessions.begin() as db:
                db.execute(insert(EvidenceContext).values(digest=digest, payload=encoded).on_conflict_do_nothing())
            self.context_cache[digest] = None
            if len(self.context_cache) > 128:
                self.context_cache.popitem(last=False)
        return {"reference": digest}

    def resolve_context(self, reference):
        if "reference" not in reference:
            return reference  # Historical full-context records remain supported.
        with self.sessions() as db:
            row = db.get(EvidenceContext, reference["reference"])
            if row is None or hashlib.sha256(row.payload.encode()).hexdigest() != reference["reference"]:
                raise ValueError("Missing or corrupt replay context")
            return json.loads(row.payload)

    def evidence_run(self, session, payload):
        encoded = json.dumps(dict(payload, storage=self.storage_audit), allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise StorageBudgetError("Operational receipt exceeds bounded size")
        with self.sessions.begin() as db:
            db.merge(EvidenceRun(session=session, payload=encoded))

    def _raw_pressure(self, ts):
        audit = dict(self.storage_audit)
        audit["raw_first_ts"] = audit["raw_first_ts"] or ts
        audit["raw_last_ts"] = ts
        # Raw replay provenance is expendable; signals/outcomes/identities/paper are not.
        # This bounded delete reuses SQLite pages, rather than requiring VACUUM.
        with self.sessions.begin() as db:
            ids = select(Record.id).where(Record.kind == "event").order_by(Record.id).limit(256)
            candidates = list(db.execute(select(Record.id, Record.ts, Record.payload).where(Record.id.in_(ids))))
            selected: list[Any] = []
            reclaimed_bytes = 0
            for row in candidates:
                if selected and reclaimed_bytes + len(row.payload.encode()) > 65536:
                    break
                selected.append(row)
                reclaimed_bytes += len(row.payload.encode())
            if selected:
                first, last = min(row.ts for row in selected), max(row.ts for row in selected)
                audit["reclaimed_first_ts"] = min(audit.get("reclaimed_first_ts", first), first)
                audit["reclaimed_last_ts"] = max(audit.get("reclaimed_last_ts", last), last)
            deleted = db.execute(delete(Record).where(Record.id.in_([row.id for row in selected])))
            audit["raw_reclaimed"] += getattr(deleted, "rowcount", 0)
            audit["raw_omitted"] += 1
            # Atomic with deletion: crash cannot erase the censorship marker.
            db.merge(EvidenceRun(session="storage", payload=json.dumps(audit)))
        self.storage_audit = audit

    def writable(self, raw=False, connection=None):
        if not self.budget:
            return True
        allocated = self.size()
        with (nullcontext(connection) if connection is not None else self.engine.connect()) as db:
            reusable: int = db.exec_driver_sql("PRAGMA freelist_count").scalar_one() * self.page_size
        physical_reserve = max(int(self.budget * .05), 262144)
        if allocated >= self.budget - physical_reserve:
            # A reader may pin WAL pages. More cleanup writes then INCREASE allocation.
            raise StorageBudgetError("Physical evidence storage reserve reached")
        if allocated - reusable >= self.budget * .85:
            if raw:
                return False
            raise StorageBudgetError("Essential evidence storage reserve reached")
        return not raw or allocated - reusable < self.budget * .70

    def persistence_snapshot(self):
        with self._proof_lock:
            return dict(self._write_proofs)

    def _verify_committed_write(self, kind, identity, expected):
        # Failed write scope has already closed/rolled back. One independent
        # committed-state read only; never retry a write or assume success.
        status = "uncertain"
        row: Any = None
        try:
            with self.engine.connect() as proof:
                if kind == "identity":
                    row = proof.execute(select(EventIdentity.event_id, EventIdentity.ts).where(
                        EventIdentity.event_id == identity)).first()
                else:
                    row = proof.execute(select(Record.kind, Record.mint, Record.session, Record.ts,
                        Record.payload).where(Record.id == identity)).first()
            if row is None:
                status = "absent"
            elif expected is None or tuple(row) == expected:
                status = "verified"
        except Exception:
            # Preserve the original write exception; unreadable evidence is UNKNOWN.
            pass
        with self._proof_lock:
            self._write_proofs[f"{kind}_{status}"] += 1
        return status == "verified"

    def reserve_event(self, event_id, ts):
        reserved = None
        try:
            with self.engine.begin() as db:
                self.writable(connection=db)
                result = db.execute(IDENTITY_INSERT, {"event_id": event_id, "ts": ts})
                reserved = getattr(result, "rowcount", 0) == 1
        except Exception:
            if reserved is not None and self._verify_committed_write(
                "identity", event_id, (event_id, ts) if reserved else None
            ):
                return reserved
            raise
        return reserved  # The transaction committed before this acknowledgement.

    def _add_event(self, payload, mint, session, ts):
        identity = 0
        encoded = None
        try:
            with self.engine.begin() as db:
                if self.writable(raw=True, connection=db):
                    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
                    if self.budget and len(encoded.encode()) > min(1048576, int(self.budget * .01)):
                        raise StorageBudgetError("Record exceeds per-write evidence reserve")
                    result = db.execute(RAW_EVENT_INSERT, dict(
                        kind="event", mint=mint, session=session, ts=ts, payload=encoded))
                    primary_key = result.inserted_primary_key
                    if primary_key is None or primary_key[0] is None:
                        raise RuntimeError("Raw event insert did not return its identity")
                    identity = primary_key[0]
        except Exception:
            if identity and self._verify_committed_write(
                "event", identity, ("event", mint, session, ts, encoded)
            ):
                return identity
            raise
        if not identity:
            self._raw_pressure(ts)
        return identity

    def add(self, kind, payload, mint="", session="", ts=None):
        ts = time.time() if ts is None else ts
        if kind == "event":
            return self._add_event(payload, mint, session, ts)
        # All financial/research records retain their original ORM flush,
        # observer transaction and acknowledgement semantics.
        with self.sessions.begin() as db:
            if self.writable(raw=False, connection=db.connection()):
                encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
                if self.budget and len(encoded.encode()) > min(1048576, int(self.budget * .01)):
                    raise StorageBudgetError("Record exceeds per-write evidence reserve")
                row = Record(kind=kind, mint=mint, session=session, ts=ts, payload=encoded)
                db.add(row)
                db.flush()
                if self.record_observer is not None and kind in ("signal", "outcome"):
                    self.record_observer(db, row, payload)
                identity = row.id
            else:
                identity = 0
        if not identity:
            self._raw_pressure(ts)
        return identity

    def checkpoint_records(self, records, session, ts):
        """Only immutable restore records; never buffers event, paper, signal or outcome writes.

        <=500 rows / 4MiB prepared data. Each commit has <=10 rows and <=64KiB,
        except one existing-valid larger record, which commits alone.
        A single per-session receipt advances atomically with each committed prefix.
        """
        prepared: list[tuple[str, str, str]] = []
        total_bytes = 0
        for kind, payload, mint in records:
            if kind not in ("snapshot", "creator_profile"):
                raise ValueError("Checkpoint record kind forbidden")
            encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
            size = len(encoded.encode())
            if self.budget and size > min(1048576, int(self.budget * .01)):
                raise StorageBudgetError("Record exceeds per-write evidence reserve")
            total_bytes += size
            if len(prepared) >= 500 or total_bytes > 4194304:
                raise StorageBudgetError("Checkpoint exceeds bounded preparation")
            prepared.append((kind, encoded, mint))
        digest = hashlib.sha256(json.dumps(prepared, sort_keys=True).encode()).hexdigest()
        key = "cp:" + session
        if len(key) > 40:
            raise ValueError("Checkpoint session too long")
        with self.sessions() as sql:
            row = sql.get(EvidenceRun, key)
            previous = json.loads(row.payload) if row else None
            if previous and previous["ts"] > ts:
                raise ValueError("Older checkpoint cannot replace newer progress")
            ids = []
            if previous and previous["ts"] == ts:
                if previous["digest"] != digest:
                    raise ValueError("Checkpoint retry changed frozen input")
                ids = previous["row_ids"]
                if len(ids) > len(prepared):
                    raise ValueError("Invalid checkpoint prefix")
                for identity, expected in zip(ids, prepared):
                    stored = sql.get(Record, identity)
                    if (stored is None or (stored.kind, stored.payload, stored.mint) != expected
                            or stored.session != session or stored.ts != ts):
                        raise ValueError("Missing or changed committed checkpoint row")
        while len(ids) < len(prepared):
            self.writable()
            stop, size = len(ids), 0
            while stop < len(prepared) and stop - len(ids) < 10:
                next_size = len(prepared[stop][1].encode())
                if stop > len(ids) and size + next_size > 65536:
                    break
                size += next_size
                stop += 1
            # No await/network call is permitted inside this synchronous transaction.
            with self.sessions.begin() as sql:
                # Claim the write prefix before reading it; another retry cannot append twice.
                sql.execute(text("BEGIN IMMEDIATE"))
                current = sql.get(EvidenceRun, key)
                progress = json.loads(current.payload) if current else None
                if progress and progress["ts"] > ts:
                    raise ValueError("Older checkpoint cannot replace newer progress")
                if progress and progress["ts"] == ts:
                    if progress["digest"] != digest:
                        raise ValueError("Checkpoint retry changed frozen input")
                    remote_ids = progress["row_ids"]
                    if remote_ids != ids:
                        if (remote_ids[:len(ids)] != ids or len(remote_ids) > len(prepared)):
                            raise ValueError("Conflicting checkpoint prefix")
                        for identity, expected in zip(remote_ids[len(ids):], prepared[len(ids):]):
                            stored = sql.get(Record, identity)
                            if (stored is None or (stored.kind, stored.payload, stored.mint) != expected
                                    or stored.session != session or stored.ts != ts):
                                raise ValueError("Missing or changed committed checkpoint row")
                        ids = remote_ids
                        continue
                batch = [Record(kind=kind, payload=payload, mint=mint, session=session, ts=ts)
                         for kind, payload, mint in prepared[len(ids):stop]]
                sql.add_all(batch)
                sql.flush()
                next_ids = ids + [row.id for row in batch]
                sql.merge(EvidenceRun(session=key, payload=json.dumps(dict(
                    ts=ts, digest=digest, row_ids=next_ids, total=len(prepared),
                    complete=stop == len(prepared)))))
            # Acknowledgement occurs only AFTER successful commit.
            ids = next_ids
        return ids

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
            "opportunity_signal": settings.outcome_retention_days * 86400,
            "opportunity_outcome": settings.outcome_retention_days * 86400,
            "manual_position_mark": settings.snapshot_retention_days * 86400,
            "manual_market_context": settings.snapshot_retention_days * 86400,
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
        cohorts_exist = inspect(self.engine).has_table("prospective_enrollments")
        with self.sessions.begin() as db:
            db.execute(
                delete(EventIdentity).where(EventIdentity.ts < now - settings.raw_retention_hours * 3600)
            )
            for kind, seconds in groups.items():
                query = delete(Record).where(Record.kind == kind, Record.ts < now - seconds)
                if kind == "signal" and cohorts_exist:
                    # Preserve source IDs and provenance; cohort outcomes have their own immutable copies.
                    query = query.where(text("records.id NOT IN (SELECT signal_id FROM prospective_enrollments)"))
                result = db.execute(query)
                count += getattr(result, "rowcount", 0)
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        return count

    def optimize(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.exec_driver_sql("VACUUM")
            conn.exec_driver_sql("PRAGMA optimize")
