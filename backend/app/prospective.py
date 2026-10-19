"""Frozen prospective bookkeeping around the existing OutcomeCollector only."""
import hashlib
import json
import math
import subprocess
import time
from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.config import ROOT
from backend.app.evaluation import strategy_version

PRIMARY = 300
SECONDARY = (15, 30, 60, 180, 600, 1800)


class CohortIntegrityError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def repository_identity():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                    cwd=ROOT, text=True).strip()
    if dirty:
        raise CohortIntegrityError("Working tree is not clean; refuse frozen cohort acquisition")
    return sha


def identity(settings):
    version, strategy = strategy_version(settings)
    return {"git_sha": repository_identity(), "strategy_version": version,
            "config_hash": digest(settings.model_dump()), "strategy_config": strategy,
            "config": settings.model_dump(), "mode": settings.mode}


def create_cohort(db, settings):
    if settings.mode not in ("OBSERVE", "PAPER"):
        raise CohortIntegrityError("Prospective research requires OBSERVE or PAPER, never DEMO")
    if set(settings.horizons) != {PRIMARY, *SECONDARY}:
        raise CohortIntegrityError("Cohort horizons must contain the fixed 300s primary and declared secondaries")
    frozen = identity(settings)
    created = time.time()
    strategy_hash = digest({key: frozen[key] for key in ("git_sha", "strategy_version", "config_hash")})
    cohort_id = f"prospective-{datetime.fromtimestamp(created, timezone.utc):%Y%m%d}-{strategy_hash[:12]}"
    manifest = {**frozen, "strategy_hash": strategy_hash, "cohort_id": cohort_id, "created_at": created,
        "created_at_utc": datetime.fromtimestamp(created, timezone.utc).isoformat(),
        "horizons": sorted(settings.horizons), "latency_ms": settings.latency_ms,
        "failed_tx_reserve_usd": settings.failed_tx_reserve_usd,
        "position_semantics": "Existing token.viability.proposed_position_usd, existing fallback 4 USD; frozen at signal",
        "min_holdout_samples": settings.min_holdout_samples,
        "minimum_primary_coverage_pct": 100,
        "primary_endpoint": {"horizon_seconds": PRIMARY, "metric": "after_cost_net_return_pct", "role": "PRIMARY"},
        "secondary_endpoints": [{"horizon_seconds": h, "role": "SECONDARY_EXPLORATORY"} for h in SECONDARY],
        "dedup": "Earliest eligible signal per token/session; later signals descriptive only",
        "session_scope": "Explicit matching cohort required for every normal session against this DB; offline replay never enrolls",
        "quality_policy": "Keep degraded sessions; report coverage, missing outcomes and infrastructure counters",
        "analysis_policy": "Interim statistics are descriptive; no automated stopping, sequential error control or approval"}
    with db.engine.begin() as connection:
        if connection.execute(text("SELECT 1 FROM prospective_cohorts WHERE cohort_id=:id"), {"id": cohort_id}).first():
            raise CohortIntegrityError("Cohort already exists; never overwrite or auto-migrate")
        connection.execute(text("INSERT INTO prospective_cohorts VALUES (:id,:manifest,:digest)"),
                           {"id": cohort_id, "manifest": canonical(manifest), "digest": digest(manifest)})
    return manifest


def read_manifest(connection, cohort_id):
    row = connection.execute(text("SELECT manifest,digest FROM prospective_cohorts WHERE cohort_id=:id"),
                             {"id": cohort_id}).first()
    if row is None:
        raise CohortIntegrityError("Unknown cohort")
    manifest = json.loads(row[0])
    if digest(manifest) != row[1] or manifest["primary_endpoint"] != {
            "horizon_seconds": PRIMARY, "metric": "after_cost_net_return_pct", "role": "PRIMARY"}:
        raise CohortIntegrityError("Frozen manifest integrity failure")
    return manifest


class ProspectiveCohort:
    def __init__(self, db, settings, cohort_id):
        self.db, self.settings, self.cohort_id = db, settings, cohort_id
        with db.engine.connect() as connection:
            self._manifest = read_manifest(connection, cohort_id)
        self.assert_current()

    @property
    def manifest(self):
        return json.loads(canonical(self._manifest))

    def assert_current(self):
        current = identity(self.settings)
        changed = [key for key in current if current[key] != self._manifest[key]]
        if changed:
            raise CohortIntegrityError("Frozen cohort drift; append refused: " + ", ".join(changed))

    def on_record(self, connection, row, payload):
        self.assert_current()
        params = {"cohort": self.cohort_id, "signal": row.id}
        if row.kind == "signal":
            if payload.get("eligible_research") is not True:
                return
            if payload.get("strategy_version") != self._manifest["strategy_version"] or payload.get("mode") != self._manifest["mode"]:
                raise CohortIntegrityError("Signal version/mode mismatch")
            if row.ts <= self._manifest["created_at"]:
                return  # Retrospective signal remains separate, never enroll history.
            if payload.get("timestamp") != row.ts or not math.isfinite(row.ts) or row.ts > time.time():
                raise CohortIntegrityError("Invalid/future signal timestamp")
            prior = connection.execute(text("""SELECT ts FROM prospective_enrollments
                WHERE cohort_id=:cohort AND session=:session AND mint=:mint AND primary_sample=1"""),
                {**params, "session": row.session, "mint": row.mint}).first()
            if prior and row.ts < prior[0]:
                raise CohortIntegrityError("Out-of-order eligible signal; immutable earliest sample cannot be replaced")
            connection.execute(text("""INSERT INTO prospective_enrollments
                VALUES (:cohort,:signal,:session,:mint,:ts,:primary,:snapshot,:acquired)"""),
                {**params, "session": row.session, "mint": row.mint, "ts": row.ts,
                 "primary": int(prior is None), "snapshot": canonical(payload), "acquired": time.time()})
        else:
            params["signal"] = payload.get("signal_id")
            enrolled = connection.execute(text("""SELECT 1 FROM prospective_enrollments
                WHERE cohort_id=:cohort AND signal_id=:signal"""), params).first()
            if not enrolled:
                return
            if (payload.get("strategy_version", self._manifest["strategy_version"]) != self._manifest["strategy_version"]
                    or payload.get("mode", self._manifest["mode"]) != self._manifest["mode"]):
                raise CohortIntegrityError("Outcome version/mode mismatch")
            horizons = (self._manifest["horizons"] if payload.get("status") == "UNAVAILABLE_CAPACITY"
                        and "horizon" not in payload else [payload.get("horizon")])
            for horizon in horizons:
                if horizon not in self._manifest["horizons"]:
                    raise CohortIntegrityError("Undeclared outcome horizon")
                connection.execute(text("""INSERT OR IGNORE INTO prospective_outcomes
                    VALUES (:cohort,:signal,:horizon,:ts,:payload,:acquired)"""),
                    {**params, "horizon": horizon, "ts": row.ts, "payload": canonical({**payload, "horizon": horizon}), "acquired": time.time()})
            if payload.get("status") == "UNAVAILABLE_CAPACITY":
                connection.execute(text("DELETE FROM prospective_pending WHERE cohort_id=:cohort AND signal_id=:signal"), params)

    def persist_pending(self, signal_id, pending):
        with self.db.engine.begin() as connection:
            params = {"cohort": self.cohort_id, "signal": signal_id}
            if pending is None:
                connection.execute(text("DELETE FROM prospective_pending WHERE cohort_id=:cohort AND signal_id=:signal"), params)
                return
            if not connection.execute(text("SELECT 1 FROM prospective_enrollments WHERE cohort_id=:cohort AND signal_id=:signal"), params).first():
                return
            self.assert_current()
            value = {**pending, "remaining": sorted(pending["remaining"])}
            connection.execute(text("""INSERT INTO prospective_pending VALUES (:cohort,:signal,:payload)
                ON CONFLICT(cohort_id,signal_id) DO UPDATE SET payload=excluded.payload"""),
                {**params, "payload": canonical(value)})

    def restore_pending(self):
        with self.db.engine.connect() as connection:
            rows = connection.execute(text("""SELECT p.signal_id,p.payload,e.snapshot FROM prospective_pending p
                JOIN prospective_enrollments e USING(cohort_id,signal_id)
                WHERE p.cohort_id=:cohort ORDER BY p.signal_id LIMIT 2001"""), {"cohort": self.cohort_id}).all()
            if len(rows) > 2000:
                raise CohortIntegrityError("Persisted collector capacity exceeded")
            result = {}
            completed = []
            for signal_id, payload, snapshot in rows:
                value = json.loads(payload)
                if value["signal"] != json.loads(snapshot):
                    raise CohortIntegrityError("Persisted pending signal snapshot changed")
                done = connection.execute(text("SELECT horizon FROM prospective_outcomes WHERE cohort_id=:cohort AND signal_id=:signal"),
                                          {"cohort": self.cohort_id, "signal": signal_id}).scalars().all()
                value["remaining"] = set(value["remaining"]) - set(done)
                if value["remaining"]:
                    result[signal_id] = value
                else:
                    completed.append(signal_id)
        for signal_id in completed:
            self.persist_pending(signal_id, None)
        return result

    def quality(self, session, payload):
        self.assert_current()
        with self.db.engine.begin() as connection:
            previous = connection.execute(text("SELECT payload FROM prospective_sessions WHERE cohort_id=:cohort AND session=:session"),
                                          {"cohort": self.cohort_id, "session": session}).scalar()
            old = json.loads(previous) if previous else {}
            unavailable = not all(payload.get("providers_connected", {}).values())
            startup = payload["updated_at"] - payload.get("started_at", 0) < 30
            payload = {**payload, "quality_samples": old.get("quality_samples", 0) + 1,
                       "storage_full_samples": old.get("storage_full_samples", 0) + int(bool(payload.get("storage_full"))),
                       "resource_pressure_samples": old.get("resource_pressure_samples", 0) + int(bool(payload.get("resource_pressure"))),
                       "startup_unavailable_samples": old.get("startup_unavailable_samples", 0) + int(unavailable and startup),
                       "unavailable_provider_samples": old.get("unavailable_provider_samples", 0) + int(unavailable and not startup)}
            connection.execute(text("""INSERT INTO prospective_sessions VALUES (:cohort,:session,:payload)
                ON CONFLICT(cohort_id,session) DO UPDATE SET payload=excluded.payload"""),
                {"cohort": self.cohort_id, "session": session, "payload": canonical(payload)})
