"""Bounded append-only pilot accounting, separate from cohorts and outcomes.

One serial writer per file (Linux/WSL advisory lock). Durable acknowledgements
follow SQLite commit; no network, raw receipts or unbounded pending queue.
"""

import fcntl
import json
import math
from pathlib import Path
import re
import sqlite3

from backend.app.early_edge_quote_receipts import Receipt, Result, digest, validate_receipt

STAGES = ("SIGNAL", "CONTROL", "ENTRY_QUOTE", "EXIT_QUOTE")
DISPOSITIONS = {
    "ELIGIBLE": {"ELIGIBLE"},
    "INELIGIBLE": {"HARD_RISK", "UNITS_MISSING", "READINESS_MISSING", "STALE_EVIDENCE",
                   "LIFECYCLE_INELIGIBLE", "PROVIDER_DISAGREEMENT", "CREATOR_SELLING"},
    "MATCHED": {"SELECTED_AT_T"},
    "NOT_SELECTED": {"OTHER_CONTROL_SELECTED"},
    "UNMATCHED": {"NO_COMPARABLE_CONTROL", "CONTROL_ALREADY_USED", "AMBIGUOUS_CONTROL"},
    "QUOTE_ACCEPTED": {"VALID_RECEIPT"},
    "QUOTE_NOT_SELECTED": {"FIRST_VALID_ALREADY_RECORDED"},
    "UNAVAILABLE_QUOTE": {"MISSING_RECEIPT", "INCOMPLETE_RECEIPT", "INCOMPLETE_OR_UNSUPPORTED_RECEIPT",
                          "SOURCE_MISMATCH", "IDENTITY_OR_DIRECTION_MISMATCH", "VENUE_INCOMPATIBLE",
                          "MIGRATION_EVIDENCE_REQUIRED", "STALE_OR_FUTURE_PROVIDER_QUOTE",
                          "MISSING_PROVIDER_TIME_OR_CONTEXT", "EXPIRED_QUOTE", "NO_ROUTE",
                          "INCONSISTENT_SLIPPAGE_OR_OUTPUT", "INCOMPLETE_COST_LEDGER",
                          "COST_COMPONENT_UNAVAILABLE", "UNVERIFIED_COST_COMPONENT",
                          "INCONSISTENT_COST_COMPONENT", "INVALID_TIME"},
    "UNAVAILABLE_UNITS": {"UNITS_OR_AMOUNT_MISMATCH", "UNSUPPORTED_UNITS", "COST_UNITS_UNAVAILABLE"},
    "UNAVAILABLE_PROVIDER_GAP": {"LATE_OR_OUT_OF_WINDOW", "PROVIDER_TIMEOUT", "RATE_LIMITED", "REQUEST_TIME_MISMATCH"},
    "UNAVAILABLE_INFRASTRUCTURE": {"PROCESS_INTERRUPTION", "CANCELLED", "CAPACITY_CENSORSHIP", "STORAGE_CENSORSHIP"},
    "UNAVAILABLE_OTHER": {"UNSUPPORTED_CONDITIONS"},
}
HASH = re.compile(r"^[a-f0-9]{64}$")


class LedgerError(ValueError):
    pass


class LedgerCensored(LedgerError):
    """The censorship receipt committed; caller must stop, not retry past limits."""


class AttemptLedger:
    def __init__(self, path, protocol_sha256, now, max_events=10000):
        self.path = Path(path).resolve()
        self._hash(protocol_sha256)
        self._time(now)
        if type(max_events) is not int or not 4 <= max_events <= 10000:
            raise LedgerError("Invalid ledger bound")
        # Refuse foreign/old research DBs BEFORE journal/DDL/write operations.
        if self.path.exists():
            with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables and tables != {"ee_attempt_meta", "ee_attempt_events"}:
                    raise LedgerError("Foreign database forbidden")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = open(str(self.path) + ".lock", "ab")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(self.path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA wal_autocheckpoint=32")
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS ee_attempt_meta(protocol TEXT NOT NULL, max_events INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ee_attempt_events(
              id INTEGER PRIMARY KEY, attempt TEXT NOT NULL, observation TEXT NOT NULL,
              stage TEXT NOT NULL, event TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
              at REAL NOT NULL, evidence TEXT NOT NULL, receipt TEXT, previous TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ee_attempt_lookup ON ee_attempt_events(attempt,id);
            """)
            meta = self.db.execute("SELECT * FROM ee_attempt_meta").fetchall()
            if not meta:
                self.db.execute("INSERT INTO ee_attempt_meta VALUES(?,?)", (protocol_sha256, max_events))
                self.db.commit()
            elif len(meta) != 1 or tuple(meta[0]) != (protocol_sha256, max_events):
                raise LedgerError("Ledger protocol/bound drift")
            for table in ("ee_attempt_meta", "ee_attempt_events"):
                for verb in ("UPDATE", "DELETE"):
                    self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{verb} BEFORE {verb} ON {table} "
                                    "BEGIN SELECT RAISE(ABORT,'immutable attempt ledger'); END")
            self.max_events = max_events
            self.verify()
            self.censored = bool(self.db.execute("SELECT 1 FROM ee_attempt_events WHERE event='CENSOR'").fetchone())
            if not self.censored:
                # No resumption/backfill: pending work from the prior owner is unavailable.
                pending = self.db.execute("SELECT * FROM ee_attempt_events a WHERE event='BEGIN' AND NOT EXISTS "
                    "(SELECT 1 FROM ee_attempt_events b WHERE b.attempt=a.attempt AND b.event='END')").fetchall()
                for row in pending:
                    self.finish(row["attempt"], "UNAVAILABLE_INFRASTRUCTURE", "PROCESS_INTERRUPTION", now)
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    @staticmethod
    def _hash(value):
        if not isinstance(value, str) or not HASH.fullmatch(value):
            raise LedgerError("A SHA256 evidence reference is required")

    @staticmethod
    def _time(value):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise LedgerError("Invalid observation time")

    def _append(self, attempt, observation, stage, event, status, reason, at, evidence, receipt=None):
        if self.censored:
            raise LedgerCensored("Ledger closed by censorship")
        self._time(at)
        if receipt is not None and (not isinstance(receipt, str) or len(receipt.encode()) > 12288):
            raise LedgerError("Bounded normalized receipt required")
        last = self.db.execute("SELECT * FROM ee_attempt_events ORDER BY id DESC LIMIT 1").fetchone()
        if last and at < last["at"]:
            raise LedgerError("Out-of-order ledger time")
        count = self.db.execute("SELECT count(*) FROM ee_attempt_events").fetchone()[0]
        censor = count >= self.max_events - 1
        if censor:
            event, status, reason = "CENSOR", "UNAVAILABLE_INFRASTRUCTURE", "STORAGE_CENSORSHIP"
        row = dict(attempt=attempt, observation=observation, stage=stage, event=event,
                   status=status, reason=reason, at=float(at), evidence=evidence, receipt=receipt,
                   previous=last["hash"] if last else "0" * 64)
        stamp = digest(row)
        # A failed/ambiguous commit gets no successful acknowledgement. Reopen/replay
        # by stable IDs to inspect durability; never overwrite prior rows.
        with self.db:
            self.db.execute("INSERT INTO ee_attempt_events(attempt,observation,stage,event,status,reason,at,evidence,receipt,previous,hash) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*row.values(), stamp))
        if censor:
            self.censored = True
            raise LedgerCensored("Storage censorship recorded; stop pilot")
        return stamp

    def begin(self, attempt, observation, stage, at, evidence):
        """Call BEFORE eligibility, matching or provider work; retries need new IDs."""
        for h in (attempt, observation, evidence):
            self._hash(h)
        if stage not in STAGES:
            raise LedgerError("Unknown attempt stage")
        prior = self.db.execute("SELECT * FROM ee_attempt_events WHERE attempt=? ORDER BY id LIMIT 1", (attempt,)).fetchone()
        if prior:
            same = (prior["observation"], prior["stage"], prior["evidence"]) == (observation, stage, evidence)
            self._append(attempt, prior["observation"], prior["stage"], "DUPLICATE", "DUPLICATE_DELIVERY",
                         "IDENTICAL" if same else "CONFLICT", at, evidence)
            if not same:
                raise LedgerError("Conflicting attempt identity")
            return False
        pending = self.summary()["pending_attempts"]
        self._append(attempt, observation, stage, "BEGIN", "PENDING", "ATTEMPT_STARTED", at, evidence)
        if pending >= 64:
            self.finish(attempt, "UNAVAILABLE_INFRASTRUCTURE", "CAPACITY_CENSORSHIP", at)
            return False
        return True

    def finish(self, attempt, status, reason, at, evidence=None):
        if status in ("QUOTE_ACCEPTED", "QUOTE_NOT_SELECTED"):
            raise LedgerError("Use validated quote receipt path")
        return self._finish(attempt, status, reason, at, evidence)

    def quote(self, attempt, payload, context, at):
        start = self.db.execute("SELECT stage,at,observation FROM ee_attempt_events WHERE attempt=? AND event='BEGIN'", (attempt,)).fetchone()
        if start is None or start["stage"] != ("ENTRY_QUOTE" if context.direction == "BUY" else "EXIT_QUOTE"):
            raise LedgerError("Quote attempt/direction mismatch")
        result = validate_receipt(payload, context, at)
        proof = digest(dict(receipt=result.receipt_sha256, context=result.context_sha256,
                            malformed_reason=result.reason if result.receipt_sha256 is None else None))
        prior = self.db.execute("SELECT evidence FROM ee_attempt_events WHERE attempt=? AND event='END'", (attempt,)).fetchone()
        if prior:
            if result.receipt_sha256 is None:
                # Invalid raw payloads aren't retained or hashed without a bound;
                # equal validation errors don't prove byte-identical delivery.
                self._append(attempt, start["observation"], start["stage"], "DUPLICATE", "DUPLICATE_DELIVERY",
                             "UNVERIFIABLE", at, proof)
                return Result(accepted=False, status="UNAVAILABLE_QUOTE", reason="DUPLICATE_UNVERIFIABLE",
                              context_sha256=result.context_sha256)
            same = prior["evidence"] == proof
            self._append(attempt, start["observation"], start["stage"], "DUPLICATE", "DUPLICATE_DELIVERY",
                         "IDENTICAL" if same else "CONFLICT", at, proof)
            if not same:
                raise LedgerError("Conflicting terminal observation")
            # A replay is never a fresh quote, even when the original was accepted.
            return Result(accepted=False, status="UNAVAILABLE_QUOTE", reason="DUPLICATE_IGNORED",
                          receipt_sha256=result.receipt_sha256, context_sha256=result.context_sha256)
        if result.accepted and payload["requested_at"] != start["at"]:
            result = Result(accepted=False, status="UNAVAILABLE_PROVIDER_GAP", reason="REQUEST_TIME_MISMATCH",
                            receipt_sha256=result.receipt_sha256, context_sha256=result.context_sha256)
        if result.accepted and self.db.execute(
            "SELECT 1 FROM ee_attempt_events WHERE observation=? AND stage=? AND event='END' AND status='QUOTE_ACCEPTED'",
            (start["observation"], start["stage"]),
        ).fetchone():
            result = Result(accepted=False, route_valid=True, status="QUOTE_NOT_SELECTED",
                            reason="FIRST_VALID_ALREADY_RECORDED", receipt_sha256=result.receipt_sha256,
                            context_sha256=result.context_sha256)
        normalized = None
        if result.receipt_sha256 is not None:
            normalized = json.dumps(dict(receipt=Receipt.model_validate(payload).model_dump(mode="json"),
                                         context=context.model_dump(mode="json")),
                                    sort_keys=True, separators=(",", ":"), allow_nan=False)
        self._finish(attempt, result.status, result.reason, at, proof, normalized)
        return result

    def _finish(self, attempt, status, reason, at, evidence=None, receipt=None):
        self._hash(attempt)
        if status not in DISPOSITIONS or reason not in DISPOSITIONS[status]:
            raise LedgerError("Unknown disposition/reason")
        start = self.db.execute("SELECT * FROM ee_attempt_events WHERE attempt=? AND event='BEGIN'", (attempt,)).fetchone()
        if start is None:
            raise LedgerError("Attempt must be durably started first")
        if status in ("ELIGIBLE", "INELIGIBLE", "MATCHED", "UNMATCHED", "NOT_SELECTED"):
            if start["stage"] not in ("SIGNAL", "CONTROL"):
                raise LedgerError("Stage/disposition mismatch")
        elif status in ("QUOTE_ACCEPTED", "QUOTE_NOT_SELECTED") and start["stage"] not in ("ENTRY_QUOTE", "EXIT_QUOTE"):
            raise LedgerError("Stage/disposition mismatch")
        evidence = start["evidence"] if evidence is None else evidence
        self._hash(evidence)
        prior = self.db.execute("SELECT * FROM ee_attempt_events WHERE attempt=? AND event='END'", (attempt,)).fetchone()
        if prior:
            same = (prior["status"], prior["reason"], prior["evidence"]) == (status, reason, evidence)
            result = self._append(attempt, start["observation"], start["stage"], "DUPLICATE", "DUPLICATE_DELIVERY",
                                  "IDENTICAL" if same else "CONFLICT", at, evidence)
            if not same:
                raise LedgerError("Conflicting terminal observation")
            return result
        return self._append(attempt, start["observation"], start["stage"], "END", status, reason, at, evidence, receipt)

    def summary(self):
        # BEGIN and rejected-at-guard observations both remain in the denominator.
        base = "SELECT attempt,observation,stage FROM ee_attempt_events WHERE event IN ('BEGIN','CENSOR') GROUP BY attempt"
        return dict(
            unique_attempts=self.db.execute(f"SELECT count(*) FROM ({base})").fetchone()[0],
            unique_observations=self.db.execute(f"SELECT count(*) FROM (SELECT observation,stage FROM ({base}) GROUP BY observation,stage)").fetchone()[0],
            pending_attempts=self.db.execute("SELECT count(*) FROM ee_attempt_events a WHERE event='BEGIN' AND NOT EXISTS "
                "(SELECT 1 FROM ee_attempt_events b WHERE b.attempt=a.attempt AND b.event IN ('END','CENSOR'))").fetchone()[0],
            dispositions={r[0]: r[1] for r in self.db.execute("SELECT status,count(*) FROM ee_attempt_events a "
                "WHERE event='END' OR (event='CENSOR' AND NOT EXISTS "
                "(SELECT 1 FROM ee_attempt_events b WHERE b.attempt=a.attempt AND b.event='END')) GROUP BY status")},
            duplicates=self.db.execute("SELECT count(*) FROM ee_attempt_events WHERE event='DUPLICATE'").fetchone()[0],
            conflicts=self.db.execute("SELECT count(*) FROM ee_attempt_events WHERE event='DUPLICATE' AND reason='CONFLICT'").fetchone()[0],
            unverifiable_duplicates=self.db.execute("SELECT count(*) FROM ee_attempt_events WHERE event='DUPLICATE' AND reason='UNVERIFIABLE'").fetchone()[0],
            censored=self.censored,
        )

    def verify(self):
        previous = "0" * 64
        for row in self.db.execute("SELECT * FROM ee_attempt_events ORDER BY id"):
            payload = {k: row[k] for k in row.keys() if k not in ("id", "hash")}
            if row["previous"] != previous or digest(payload) != row["hash"]:
                raise LedgerError("Attempt audit integrity failure")
            previous = row["hash"]

    def close(self):
        self.db.close()
        self.lock.close()

    def shutdown(self, at):
        """Graceful cutoff: explicit cancellations, never fake completed quotes."""
        try:
            if not self.censored:
                pending = self.db.execute("SELECT attempt FROM ee_attempt_events a WHERE event='BEGIN' AND NOT EXISTS "
                    "(SELECT 1 FROM ee_attempt_events b WHERE b.attempt=a.attempt AND b.event='END')").fetchall()
                for row in pending:
                    self.finish(row["attempt"], "UNAVAILABLE_INFRASTRUCTURE", "CANCELLED", at)
            return self.summary()
        finally:
            self.close()
