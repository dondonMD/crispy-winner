"""Isolated frozen EARLY observational study. No strategy or paper approval writes."""

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid

from backend.app.config import ROOT
from backend.app.early_edge_design import LATENCIES_MS, PRIMARY_LATENCY_MS, design_fields, readiness, risk_set
from backend.app.evaluation import strategy_version
from backend.app.opportunity import load_intelligence_settings, OpportunityAction
from backend.app.early_edge_quotes import QUOTES, WSOL, QuoteUnavailable, pump_buy, quote_budget, sell

HORIZONS = (60, 180, 300, 600, 1800)
STATUSES = (
    "MEASURED",
    "ECONOMIC_ZERO_EXIT",
    "UNAVAILABLE_INFRASTRUCTURE",
    "UNAVAILABLE_QUOTE",
    "UNAVAILABLE_UNITS",
    "UNAVAILABLE_PROVIDER_GAP",
    "UNAVAILABLE_OTHER",
)
MAX_PENDING = 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class IntegrityError(ValueError):
    pass


def identity(settings, require_clean=True):
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (
        require_clean
        and subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    ):
        raise IntegrityError("Clean committed source required before creating or appending a real cohort")
    paths = sorted(
        {
            *Path(ROOT, "backend/app").glob("*.py"),
            *Path(ROOT, "backend/app").glob("*.json"),
            *Path(ROOT, "config").glob("*.yaml"),
            *Path(ROOT, "scripts").glob("early_edge*.*"),
        }
    )
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    version, config = strategy_version(settings)
    cfg = load_intelligence_settings()
    return dict(
        git_sha=sha,
        opportunity_version=cfg.version,
        opportunity_config=cfg.model_dump(),
        core_version=version,
        config_hash=digest(settings.model_dump()),
        config=settings.model_dump(),
        strategy_config=config,
        source_hashes=hashes,
        source_hash=digest(hashes),
        mode=settings.mode,
    )


def manifest(settings, now=None, draft=True, synthetic=False):
    now = time.time() if now is None else now
    if settings.mode != "OBSERVE":
        raise IntegrityError("Early-edge collection is OBSERVE only")
    current = identity(settings, require_clean=not (draft or synthetic))
    plan = dict(
        namespace="EARLY_EDGE_SYNTHETIC" if synthetic else "EARLY_EDGE",
        synthetic=synthetic,
        collectable=not draft and not synthetic,
        identity=current,
        created_at=now,
        primary_signal="First qualifying existing EARLY_OPPORTUNITY per mint/session; no graduation; verified current curve <85; no rejected/expired, hard security failure, creator sell or disagreement; canonical Pump units known",
        control="First qualifying non-EARLY existing action per mint/session in same broad early window; same safeguards; no retrospective exclusions",
        dedup="Earliest per arm/mint/session. A control may later enter treatment; retain both and bootstrap by mint across sessions/arms.",
        primary_usd=4,
        sensitivity_usd=[],
        latency_ms=10000,
        entry_max_delay_seconds=10,
        exit_max_delay_seconds=20,
        primary_horizon=300,
        secondary_horizons=[60, 180, 600, 1800],
        horizon_origin="Signal timestamp, not delayed entry timestamp",
        crowd_progress=85,
        crowd="First prospectively acquired verified curve observation >=85; first bounded subsequent executable buy quote, separately timestamped",
        scheduling="Required entry/horizon/crowd deadlines before optional 15s marks; chronological then mint; no arm preference; shared RPC limiter remains authoritative",
        mark_interval_seconds=15,
        min_primary_samples=100,
        bootstrap_resamples=10000,
        bootstrap_seed=20261020,
        analysis="Primary mean 300s net; normal CI plus mint-cluster bootstrap percentile CI; treatment-weighted stratum difference on complete common support, jointly mint-cluster bootstrapped; no causal claim",
        strata=dict(
            progress_edges=[30, 60, 75, 85],
            age_seconds_edges=[120, 300, 600],
            quote="exact mint",
            security="CURRENT_VERIFIED vs OTHER",
        ),
        strongest_status_requires="100 measured/accounted EARLY token/session samples, 100% terminal accounting, zero unavailable primary outcomes in either arm, all treatment strata have controls, positive primary and comparison bootstrap lower bounds, intact manifest/snapshots, no integrity defects",
        usd_policy="Coinbase SOL-USD ticker and Kraken USDCUSD latest public trade (count=1), publication/acquisition <= fill acquisition, <=20s old. USD4 converted at entry using already available reference, not signal FX. No pre-entry SOL/USD PnL, future interpolation or USDC par.",
        usd_reference_sources={
            WSOL: dict(
                provider="Coinbase Exchange public ticker",
                api="https://api.exchange.coinbase.com/products/SOL-USD/ticker",
                timestamp="time",
                cache_seconds=10,
                max_age_seconds=20,
            ),
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": dict(
                provider="Kraken public recent trades",
                api="https://api.kraken.com/0/public/Trades?pair=USDCUSD&count=1",
                timestamp="result.USDCUSD[0][2]",
                version="Spot REST v0",
                cache_seconds=10,
                max_age_seconds=20,
            ),
        },
        cost_model=dict(
            platform_pct=settings.platform_fee_pct,
            network_usd_per_side=settings.network_usd_per_side,
            priority_usd_per_side=settings.priority_usd_per_side,
            failed_tx_reserve_usd=settings.failed_tx_reserve_usd,
            additional_slippage_pct=1.0,
            manual_reserve_policy="1% each leg, predeclared manual execution reserve; not SDK slippage or an empirically fitted fee",
            account_close_network_usd=settings.network_usd_per_side,
            account_close_priority_usd=settings.priority_usd_per_side,
            protocol_fees="SDK included, audited explicitly exactly once",
            impact="SDK reserve math only, no extra impact charge",
            account_rent="Recoverable capital lockup, excluded from primary PnL; full non-recovery sensitivity reported separately",
            rent_policy="RECOVERABLE_CAPITAL_LOCKUP",
            manual_interface="No named interface selected; platform fee is an explicit conservative assumption, not an authoritative fee",
            funding="Quote inventory assumed funded. Base ATA rent is recoverable capital, excluded from primary net PnL; separate account-close transaction allowance included.",
        ),
        supported_quotes=list(QUOTES),
        quote_sources=json.loads(Path(__file__).with_name("early_edge_sources.json").read_text())["sources"],
        missing_rules=list(STATUSES),
        zero_exit="Only explicit verified on-chain proof with no executable economic exit; unavailable/zero SDK output is never sufficient",
        no_backfill=True,
        interruption="Every unfinished horizon becomes UNAVAILABLE_INFRASTRUCTURE; pending observations never resume after restart",
        capacity=dict(
            max_pending=MAX_PENDING,
            policy="Enroll first; terminal UNAVAILABLE_INFRASTRUCTURE on capacity. No cohort denominator exclusions.",
        ),
        secondary="EXPLORATORY only; no alternative notionals are enabled in this protocol",
        limitations=[
            "Observational selection/confounding",
            "Survivorship and unavailable-outcome risk",
            "Same-market and repeated-mint correlation",
            "Overlapping hypothetical exposure",
            "Regime dependence",
            "Secondary multiple testing",
            "Normal CI heavy-tail limitation",
            "SDK hypothetical quotes are not execution guarantees",
            "Fixed stopping does not remove regime dependence or residual market correlation",
            "No guarantee of future returns",
        ],
    )
    plan.update(design_fields(settings))
    plan["cohort_id"] = (
        ("DRAFT-" if draft else "synthetic-" if synthetic else "early-edge-")
        + datetime.fromtimestamp(now, UTC).strftime("%Y%m%d-")
        + digest(plan)[:12]
    )
    return plan


def canonical_units_known(token, now):
    return any(
        e.kind == "trade"
        and e.source == "Solana WSS"
        and 0 <= now - e.ts <= 180
        and e.currency == QUOTES.get(token.verified_quote_mint, (None,))[0]
        and e.evidence.get("units_valid") is True
        and e.evidence.get("quote_mint") == token.verified_quote_mint
        and isinstance(e.evidence.get("canonical_trade"), dict)
        for e in token.events
    )


def signal_snapshot(token, opportunity, now, settings, fx=None, require_ready=True):
    """Pure copying only: neither Token nor opportunity is mutated."""
    view = opportunity.model_dump(mode="json") if hasattr(opportunity, "model_dump") else opportunity
    cfg = load_intelligence_settings()
    f = token.features.get("180", {})
    # This unchanged mandatory gate already makes enrollment impossible. Preserve the
    # config read/drift check but avoid duplicate readiness work for unknown units.
    if token.verified_quote_mint not in QUOTES:
        return None
    curve_ok = (
        token.last_curve > 0
        and 0 <= now - token.last_curve <= cfg.curve_fresh_seconds
        and view.get("dynamics", {}).get("freshness") == "CURRENT"
        and token.curve_history
        and token.curve_history[-1] == (token.last_curve, token.curve_progress)
    )
    observed = readiness(token, now, settings)
    security = token.security
    eligible = (
        token.graduation is None
        and token.flow_venue == "PUMP"
        and token.state.value not in ("REJECTED", "EXPIRED")
        and token.decision.get("decision") != "REJECT"
        and curve_ok
        and token.curve_progress is not None
        and 0 <= token.curve_progress < 85
        and not security.get("hard_failures")
        and not token.disagreement
        and not (f.get("creator_sell_volume", 0) > 0)
        and f.get("units_valid") is True
        and token.verified_quote_mint in QUOTES
        and f.get("currency") == QUOTES[token.verified_quote_mint][0]
        and canonical_units_known(token, now)
        and (observed["ready"] or not require_ready)
    )
    if not eligible:
        return None
    return json.loads(
        canonical(
            dict(
                observation_readiness=observed,
                timestamp=now,
                mint=token.mint,
                action=view["action"],
                opportunity=view,
                opportunity_version=view["research_version"],
                state=token.state.value,
                graduation=None,
                curve_progress=token.curve_progress,
                curve_observed_at=token.last_curve,
                features=f,
                scores=token.scores,
                security=security,
                security_verified=security.get("data_quality") == "VERIFIED"
                and 0 <= now - token.last_security <= settings.security_ttl_seconds,
                decision=token.decision,
                canonical_units_known=True,
                provider_disagreement=token.disagreement,
                curve_verified=True,
                flow_venue=token.flow_venue,
                age=now - token.created,
                quote_mint=token.verified_quote_mint,
                price_descriptive_only=token.price,
                liquidity_descriptive_only=token.liquidity,
                fx=fx or {},
                mode=settings.mode,
                proposed_notional_usd=4,
                research_namespace="EARLY_EDGE",
                eligible=True,
            )
        )
    )


def stratum(snapshot, plan):
    p = plan["strata"]
    progress = next(i for i, bound in enumerate(p["progress_edges"]) if snapshot["curve_progress"] < bound)
    age = sum(snapshot["age"] >= bound for bound in p["age_seconds_edges"])
    return canonical([progress, age, snapshot["quote_mint"], bool(snapshot["security_verified"])])


def fx_value(refs, mint, at):
    if mint not in QUOTES:
        raise QuoteUnavailable("UNAVAILABLE_UNITS")
    ref = refs.get(mint)
    expected = (
        ("Coinbase Exchange public ticker", "SOL-USD")
        if mint == WSOL
        else ("Kraken public recent trades", "USDCUSD")
    )
    if not ref or (ref.get("source"), ref.get("product")) != expected:
        raise QuoteUnavailable()
    for stamp in (ref["published_at"], ref["acquired_at"]):
        if not math.isfinite(stamp) or not 0 <= at - stamp <= 20:
            raise QuoteUnavailable()
    price = ref["usd"]
    if not math.isfinite(price) or price <= 0:
        raise QuoteUnavailable()
    return price


class Study:
    """Separate SQLite namespace; immutable manifest, signals and terminal outcomes."""

    def __init__(self, path, settings, cohort=None, synthetic=False):
        self.path, self.settings, self.synthetic = Path(path).resolve(), settings, synthetic
        if self.path in {ROOT / "data/prospective.db", ROOT / "data/radar.db", ROOT / "data/demo.db"}:
            raise IntegrityError("Existing core/research database forbidden")
        if self.path.exists():
            check = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check.close()
            if tables and "ee_manifest" not in tables:
                raise IntegrityError("Foreign database forbidden")
        elif cohort is None:
            raise IntegrityError("Explicit manifest required to create a new isolated study")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS ee_manifest(id TEXT PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ee_sessions(id TEXT PRIMARY KEY,started REAL NOT NULL,ended REAL);
        CREATE TABLE IF NOT EXISTS ee_signals(id INTEGER PRIMARY KEY,session TEXT NOT NULL,mint TEXT NOT NULL,arm TEXT NOT NULL,ts REAL NOT NULL,stratum TEXT NOT NULL,snapshot TEXT NOT NULL,hash TEXT NOT NULL,UNIQUE(session,mint,arm));
        CREATE TABLE IF NOT EXISTS ee_repeats(session TEXT,mint TEXT,arm TEXT,n INTEGER NOT NULL,PRIMARY KEY(session,mint,arm));
        CREATE TABLE IF NOT EXISTS ee_entries(signal INTEGER PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ee_lifecycle(session TEXT,mint TEXT,kind TEXT,ts REAL,payload TEXT NOT NULL,PRIMARY KEY(session,mint,kind));
        CREATE TABLE IF NOT EXISTS ee_pending(signal INTEGER,latency_ms INTEGER,payload TEXT NOT NULL,PRIMARY KEY(signal,latency_ms));
        CREATE TABLE IF NOT EXISTS ee_pairs(treatment INTEGER PRIMARY KEY REFERENCES ee_signals(id),control INTEGER UNIQUE REFERENCES ee_signals(id),risk_count INTEGER,reason TEXT,hash TEXT);
        CREATE TABLE IF NOT EXISTS ee_closure(id INTEGER PRIMARY KEY CHECK(id=1),ts REAL,reason TEXT);
        CREATE TABLE IF NOT EXISTS ee_secondary_entries(signal INTEGER,latency_ms INTEGER,payload TEXT,hash TEXT,PRIMARY KEY(signal,latency_ms));
        CREATE TABLE IF NOT EXISTS ee_secondary_outcomes(signal INTEGER,latency_ms INTEGER,horizon INTEGER,status TEXT,payload TEXT,hash TEXT,PRIMARY KEY(signal,latency_ms,horizon));
        CREATE TABLE IF NOT EXISTS ee_outcomes(signal INTEGER,horizon INTEGER,status TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(signal,horizon));
        CREATE TABLE IF NOT EXISTS ee_benchmarks(signal INTEGER,kind TEXT,ts REAL,payload TEXT NOT NULL,PRIMARY KEY(signal,kind));
        CREATE TABLE IF NOT EXISTS ee_coverage(session TEXT,mint TEXT,payload TEXT,PRIMARY KEY(session,mint));
        CREATE TABLE IF NOT EXISTS ee_quality(id INTEGER PRIMARY KEY,session TEXT,ts REAL,payload TEXT NOT NULL);
        """)
        for table in (
            "ee_pairs",
            "ee_closure",
            "ee_secondary_entries",
            "ee_secondary_outcomes",
            "ee_manifest",
            "ee_signals",
            "ee_entries",
            "ee_lifecycle",
            "ee_outcomes",
            "ee_benchmarks",
            "ee_quality",
        ):
            for verb in ("UPDATE", "DELETE"):
                self.db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_{verb} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT,'immutable early-edge research'); END"
                )
        row = self.db.execute("SELECT * FROM ee_manifest").fetchone()
        if row is None:
            if (
                not cohort
                or cohort.get("synthetic") != synthetic
                or (not synthetic and not cohort.get("collectable"))
            ):
                raise IntegrityError("Draft/synthetic manifests cannot collect real observations")
            self.db.execute(
                "INSERT INTO ee_manifest VALUES(?,?,?)",
                (cohort["cohort_id"], canonical(cohort), digest(cohort)),
            )
            self.db.commit()
        elif cohort is not None and canonical(cohort) != row["payload"]:
            raise IntegrityError("Existing manifest cannot be replaced")
        self._plan = json.loads(self.db.execute("SELECT payload FROM ee_manifest").fetchone()[0])
        self.assert_integrity()
        self.session = None

    @property
    def plan(self):
        return json.loads(canonical(self._plan))

    def assert_integrity(self):
        row = self.db.execute("SELECT * FROM ee_manifest").fetchone()
        p = json.loads(row["payload"])
        if (
            p != self._plan
            or digest(p) != row["hash"]
            or p["primary_horizon"] != 300
            or p["primary_usd"] != 4
            or p["latency_ms"] != 10000
            or p.get("design_version") != 2
            or p["synthetic"] != self.synthetic
        ):
            raise IntegrityError("Manifest integrity failure")
        if not self.synthetic:
            from backend.app.early_edge_parity import validate_attestation

            validate_attestation(p, p.get("parity_attestation", {}), p["created_at"])
        if identity(self.settings, require_clean=not self.synthetic) != p["identity"]:
            raise IntegrityError("Git/config/opportunity/source drift; new cohort required")
        return p

    def begin(self, now=None):
        now = time.time() if now is None else now
        self.assert_integrity()
        if now < self.plan["created_at"]:
            raise IntegrityError("Session predates manifest")
        # No restoration/backfill: any unfinished session was interrupted.
        for row in list(self.db.execute("SELECT signal,payload FROM ee_pending")):
            pending = json.loads(row["payload"])
            self.unavailable(
                row["signal"], pending, "UNAVAILABLE_INFRASTRUCTURE", "PROCESS_INTERRUPTION", now
            )
        self.db.execute("UPDATE ee_sessions SET ended=? WHERE ended IS NULL", (now,))
        self.session = str(uuid.uuid4())
        self.db.execute("INSERT INTO ee_sessions VALUES(?,?,NULL)", (self.session, now))
        self.db.commit()
        return self.session

    def enrollment_state(self, now):
        self.assert_integrity()
        closed = self.db.execute("SELECT ts,reason FROM ee_closure").fetchone()
        deadline = self.plan["created_at"] + 30 * 86400
        n = self.db.execute("SELECT count(*) FROM ee_signals WHERE arm='EARLY'").fetchone()[0]
        if not closed and (now >= deadline or n >= 100):
            self.db.execute(
                "INSERT INTO ee_closure VALUES(1,?,?)",
                (deadline if now >= deadline else now, "CALENDAR_LIMIT" if now >= deadline else "TARGET_N"),
            )
            self.db.commit()
            closed = self.db.execute("SELECT ts,reason FROM ee_closure").fetchone()
        return dict(
            closed=bool(closed),
            reason=closed["reason"] if closed else None,
            closed_at=closed["ts"] if closed else None,
            treatments=n,
        )

    def enroll(self, snapshot, now=None, controls=()):
        now = time.time() if now is None else now
        if not isinstance(snapshot, dict) or snapshot.get("action") != "EARLY_OPPORTUNITY":
            raise IntegrityError("Only treatment-triggered risk sets may enroll")
        if self.enrollment_state(now)["closed"]:
            return None
        # Both snapshots are validated at exactly T; matching never queries future state.
        candidates = [c for c in controls if c is not None]
        for c in candidates:
            self.validate_snapshot(c, now)
        self.db.execute("SAVEPOINT enrollment")
        try:
            tid = self._enroll_one(snapshot, now)
            if tid is None:
                self.db.execute("RELEASE enrollment")
                return None
            used = {
                r[0]
                for r in self.db.execute(
                    "SELECT mint FROM ee_signals WHERE session=? AND arm='CONTROL'", (self.session,)
                )
            }
            selected = risk_set(snapshot, candidates, self.plan, used)
            cid = self._enroll_one(selected[0], now) if selected else None
            pair = dict(
                treatment=tid,
                control=cid,
                risk_count=len(selected),
                reason="MATCHED" if cid else "UNMATCHED_AT_T",
            )
            self.db.execute(
                "INSERT INTO ee_pairs VALUES(?,?,?,?,?)",
                (tid, cid, len(selected), pair["reason"], digest(pair)),
            )
            self.db.execute("RELEASE enrollment")
            self.db.commit()
        except Exception:
            self.db.execute("ROLLBACK TO enrollment")
            self.db.execute("RELEASE enrollment")
            raise
        self.enrollment_state(now)
        return tid

    def validate_snapshot(self, snapshot, now):
        # Shared validation is performed by _enroll_one before any insertion.
        return self._enroll_one(snapshot, now, validate_only=True)

    def _enroll_one(self, snapshot, now=None, validate_only=False):
        now = time.time() if now is None else now
        self.assert_integrity()
        s = json.loads(canonical(snapshot))
        if not isinstance(s, dict):
            raise IntegrityError("Signal snapshot required")
        if (
            not self.session
            or s.get("eligible") is not True
            or s.get("opportunity_version") != self.plan["identity"]["opportunity_version"]
            or s.get("mode") != "OBSERVE"
        ):
            raise IntegrityError("Enrollment identity/eligibility failure")
        session_start = self.db.execute(
            "SELECT started FROM ee_sessions WHERE id=?", (self.session,)
        ).fetchone()[0]
        if (
            not self.plan["created_at"] < s["timestamp"] <= now
            or s["timestamp"] < session_start
            or now - s["timestamp"] > 20
        ):
            raise IntegrityError("Historical/future enrollment refused")
        if (
            s.get("observation_readiness", {}).get("ready") is not True
            or s.get("graduation") is not None
            or s.get("state") in ("REJECTED", "EXPIRED")
            or s.get("canonical_units_known") is not True
            or s.get("flow_venue") != "PUMP"
            or s.get("curve_verified") is not True
            or not 0 <= s["curve_progress"] < 85
            or s.get("provider_disagreement")
            or s["security"].get("hard_failures")
            or s["features"].get("creator_sell_volume", 0) > 0
            or s["features"].get("units_valid") is not True
            or s["quote_mint"] not in QUOTES
            or s["features"].get("currency") != QUOTES[s["quote_mint"]][0]
            or s["action"] not in {a.value for a in OpportunityAction}
            or s["opportunity"].get("research_version") != s["opportunity_version"]
            or s["opportunity"].get("dynamics", {}).get("freshness") != "CURRENT"
            or not 0
            <= s["timestamp"] - s["curve_observed_at"]
            <= load_intelligence_settings().curve_fresh_seconds
            or s["age"] < 0
            or s["decision"].get("decision") == "REJECT"
            or s["opportunity"].get("action") != s["action"]
        ):
            raise IntegrityError("Invalid primary/control signal snapshot")
        r = s["observation_readiness"]
        floor_n, floor_duration = (
            (3, load_intelligence_settings().progression_min_seconds) if s["security_verified"] else (4, 120)
        )
        if (
            r.get("checked_at") != s["timestamp"]
            or r.get("curve_observation_count", 0) < floor_n
            or r.get("coverage_seconds", 0) < floor_duration
            or r.get("largest_observation_gap", float("inf"))
            > load_intelligence_settings().curve_fresh_seconds
        ):
            raise IntegrityError("Observation-readiness floor not met")
        if validate_only:
            return None
        arm = "EARLY" if s["action"] == "EARLY_OPPORTUNITY" else "CONTROL"
        existing = self.db.execute(
            "SELECT id,ts FROM ee_signals WHERE session=? AND mint=? AND arm=?",
            (self.session, s["mint"], arm),
        ).fetchone()
        if existing:
            if s["timestamp"] < existing["ts"]:
                raise IntegrityError("Out-of-order signal refused")
            self.db.execute(
                "INSERT INTO ee_repeats VALUES(?,?,?,1) ON CONFLICT(session,mint,arm) DO UPDATE SET n=n+1",
                (self.session, s["mint"], arm),
            )
            return None
        row = self.db.execute(
            "INSERT INTO ee_signals(session,mint,arm,ts,stratum,snapshot,hash) VALUES(?,?,?,?,?,?,?)",
            (self.session, s["mint"], arm, s["timestamp"], stratum(s, self.plan), canonical(s), digest(s)),
        )
        sid = row.lastrowid
        if arm == "EARLY":
            for observed in self.db.execute(
                "SELECT * FROM ee_lifecycle WHERE session=? AND mint=?", (self.session, s["mint"])
            ):
                self.db.execute(
                    "INSERT OR IGNORE INTO ee_benchmarks VALUES(?,?,?,?)",
                    (sid, observed["kind"], observed["ts"], observed["payload"]),
                )
        pending = dict(
            snapshot=s,
            remaining=list(HORIZONS),
            entry=None,
            min=None,
            max=None,
            peak=None,
            drawdown=0,
            drawdown_pct=0,
            marks=0,
            last=None,
            last_failure="UNAVAILABLE_QUOTE",
        )
        capacity = (
            self.db.execute("SELECT count(DISTINCT signal) FROM ee_pending").fetchone()[0] >= MAX_PENDING
        )
        for latency in LATENCIES_MS:
            p = dict(pending, latency_ms=latency)
            if capacity:
                self.unavailable(sid, p, "UNAVAILABLE_INFRASTRUCTURE", "RESEARCH_CAPACITY", now)
            else:
                self.db.execute("INSERT INTO ee_pending VALUES(?,?,?)", (sid, latency, canonical(p)))

        return sid

    def outcome(self, sid, horizon, payload, latency_ms=PRIMARY_LATENCY_MS):
        if payload["status"] not in STATUSES:
            raise IntegrityError("Unknown terminal status")
        if payload["status"] == "ECONOMIC_ZERO_EXIT":
            raise IntegrityError(
                "No reviewed canonical economic-zero proof rule; automatic classification disabled"
            )
        if latency_ms == PRIMARY_LATENCY_MS:
            self.db.execute(
                "INSERT INTO ee_outcomes VALUES(?,?,?,?,?)",
                (sid, horizon, payload["status"], canonical(payload), digest(payload)),
            )
        else:
            self.db.execute(
                "INSERT INTO ee_secondary_outcomes VALUES(?,?,?,?,?,?)",
                (sid, latency_ms, horizon, payload["status"], canonical(payload), digest(payload)),
            )

    def unavailable(self, sid, pending, status, reason, now):
        for horizon in pending["remaining"]:
            self.outcome(
                sid, horizon, dict(status=status, reason=reason, recorded_at=now), pending["latency_ms"]
            )
        self.db.execute(
            "DELETE FROM ee_pending WHERE signal=? AND latency_ms=?", (sid, pending["latency_ms"])
        )

    def expire(self, now=None):
        now = time.time() if now is None else now
        self.assert_integrity()
        self.enrollment_state(now)
        for row in list(self.db.execute("SELECT * FROM ee_pending")):
            p = json.loads(row["payload"])
            s = p["snapshot"]
            if (
                p["entry"] is None
                and now > s["timestamp"] + p["latency_ms"] / 1000 + self.plan["entry_max_delay_seconds"]
            ):
                self.unavailable(row["signal"], p, p["last_failure"], "ENTRY_WINDOW_EXHAUSTED", now)
                continue
            for horizon in list(p["remaining"]):
                if now > s["timestamp"] + horizon + self.plan["exit_max_delay_seconds"]:
                    self.outcome(
                        row["signal"],
                        horizon,
                        dict(status=p["last_failure"], reason="EXIT_WINDOW_EXHAUSTED", recorded_at=now),
                        p["latency_ms"],
                    )
                    p["remaining"].remove(horizon)
            self.save(row["signal"], p)
        self.db.commit()

    def save(self, sid, pending):
        if pending["remaining"]:
            self.db.execute(
                "UPDATE ee_pending SET payload=? WHERE signal=? AND latency_ms=?",
                (canonical(pending), sid, pending["latency_ms"]),
            )
        else:
            self.db.execute(
                "DELETE FROM ee_pending WHERE signal=? AND latency_ms=?", (sid, pending["latency_ms"])
            )

    def observe_state(self, observation, refs, now=None):
        now = time.time() if now is None else now
        self.assert_integrity()
        if (
            observation.commitment != "confirmed"
            or observation.acquired_at - observation.requested_at > 5
            or (
                not self.synthetic
                and (
                    not observation.identity_address
                    or len(observation.account_addresses) != len(observation.account_hashes)
                )
            )
            or type(observation.slot) is not int
            or observation.slot < 0
            or len(observation.account_hashes) < 5
            or not (
                0 < observation.requested_at <= observation.acquired_at <= now
                and now - observation.acquired_at <= 20
            )
        ):
            raise IntegrityError("Invalid/stale/future state observation")
        self.expire(now)
        for row in list(self.db.execute("SELECT * FROM ee_pending")):
            p = json.loads(row["payload"])
            s = p["snapshot"]
            if s["mint"] != observation.mint or (
                p["last"] is not None and observation.acquired_at <= p["last"]
            ):
                continue
            state = observation.data
            if state.get("diagnostic_identity_only"):
                raise IntegrityError("Diagnostic-only pool identity cannot enter cohort outcomes")
            if state["quote_mint"] != s["quote_mint"]:
                p["last_failure"] = "UNAVAILABLE_UNITS"
                self.save(row["signal"], p)
                continue
            try:
                if p["entry"] is None:
                    if (
                        observation.requested_at < s["timestamp"] + p["latency_ms"] / 1000
                        or observation.acquired_at
                        > s["timestamp"] + p["latency_ms"] / 1000 + self.plan["entry_max_delay_seconds"]
                        or state["venue"] != "PUMP"
                    ):
                        continue
                    reference = fx_value(refs, s["quote_mint"], observation.acquired_at)
                    budget = quote_budget(4, reference, s["quote_mint"])
                    entry = pump_buy(state, budget)
                    unit = reference / 10 ** QUOTES[s["quote_mint"]][1]
                    entry.update(
                        signal_timestamp=s["timestamp"],
                        latency_ms=p["latency_ms"],
                        latency_boundary=s["timestamp"] + p["latency_ms"] / 1000,
                        quote_mint=s["quote_mint"],
                        sources=self.plan["quote_sources"],
                        state=asdict(observation),
                        unit_usd=unit,
                        cash_left_usd=4 - entry["quote_raw"] * unit,
                        rent_usd=observation.rent_lamports
                        / 1e9
                        * fx_value(refs, WSOL, observation.acquired_at),
                        entry_usd_reference=refs[s["quote_mint"]],
                        rent_usd_reference=refs[WSOL],
                    )
                    p["entry"] = entry
                    if p["latency_ms"] == PRIMARY_LATENCY_MS:
                        self.db.execute(
                            "INSERT INTO ee_entries VALUES(?,?,?)",
                            (row["signal"], canonical(entry), digest(entry)),
                        )
                    else:
                        self.db.execute(
                            "INSERT INTO ee_secondary_entries VALUES(?,?,?,?)",
                            (row["signal"], p["latency_ms"], canonical(entry), digest(entry)),
                        )
                exit_quote = sell(state, p["entry"]["quantity"])
                unit = (
                    fx_value(refs, s["quote_mint"], observation.acquired_at)
                    / 10 ** QUOTES[s["quote_mint"]][1]
                )
                result = result_costs(self.plan, p["entry"], exit_quote, unit, observation)
                result["exit_usd_reference"] = refs[s["quote_mint"]]
                p["min"] = (
                    result["net_return_pct"] if p["min"] is None else min(p["min"], result["net_return_pct"])
                )
                p["max"] = (
                    result["net_return_pct"] if p["max"] is None else max(p["max"], result["net_return_pct"])
                )
                p["peak"] = max(0 if p["peak"] is None else p["peak"], result["net_return_pct"])
                p["drawdown"] = max(p["drawdown"], p["peak"] - result["net_return_pct"])
                p["drawdown_pct"] = max(
                    p.get("drawdown_pct", 0), 100 * (p["peak"] - result["net_return_pct"]) / (100 + p["peak"])
                )
                p["marks"] += 1
                p["last"] = observation.acquired_at
                for horizon in list(p["remaining"]):
                    due = s["timestamp"] + horizon
                    if observation.requested_at < due:
                        continue  # No old request, last price carry-forward or future-best selection.
                    result_h = dict(
                        result,
                        status="MEASURED",
                        horizon=horizon,
                        recorded_at=now,
                        exit_delay_seconds=observation.acquired_at - due,
                        mfe_observed_pct=p["max"],
                        mae_observed_pct=p["min"],
                        observed_drawdown_pp=p["drawdown"],
                        observed_max_drawdown_pct=p["drawdown_pct"],
                        observed_marks=p["marks"],
                        zero_exit_evidence=None,
                    )
                    self.outcome(row["signal"], horizon, result_h, p["latency_ms"])
                    p["remaining"].remove(horizon)
            except QuoteUnavailable as exc:
                p["last_failure"] = exc.reason
            self.save(row["signal"], p)
        self.db.commit()

    def failure(self, mint, reason, now=None):
        if reason not in STATUSES or not reason.startswith("UNAVAILABLE_"):
            raise IntegrityError("Unavailable reason required")
        self.assert_integrity()
        for row in list(self.db.execute("SELECT * FROM ee_pending")):
            p = json.loads(row["payload"])
            if p["snapshot"]["mint"] == mint:
                p["last_failure"] = reason
                self.save(row["signal"], p)
        self.db.commit()

    def benchmark(self, mint, kind, ts, payload):
        self.assert_integrity()
        if kind not in ("CROWD_85", "CROWD_QUOTE", "BUYER_CROWD", "BUYER_QUOTE", "GRADUATION"):
            raise IntegrityError("Unknown benchmark")
        for row in self.db.execute(
            "SELECT id,ts FROM ee_signals WHERE mint=? AND session=? AND arm='EARLY'", (mint, self.session)
        ):
            if kind in ("CROWD_85", "BUYER_CROWD", "GRADUATION") or ts >= row["ts"]:
                self.db.execute(
                    "INSERT OR IGNORE INTO ee_benchmarks VALUES(?,?,?,?)",
                    (row["id"], kind, ts, canonical(payload)),
                )
        self.db.commit()

    def record_lifecycle(self, mint, kind, ts, payload):
        self.assert_integrity()
        if not self.session or kind not in ("CROWD_85", "BUYER_CROWD", "GRADUATION"):
            raise IntegrityError("Invalid lifecycle observation")
        started = self.db.execute("SELECT started FROM ee_sessions WHERE id=?", (self.session,)).fetchone()[0]
        if (
            not math.isfinite(ts)
            or not math.isfinite(payload.get("observed_at", float("nan")))
            or payload["observed_at"] < started
            or ts > payload["observed_at"]
        ):
            raise IntegrityError("Lifecycle acquisition provenance required")
        self.db.execute(
            "INSERT OR IGNORE INTO ee_lifecycle VALUES(?,?,?,?,?)",
            (self.session, mint, kind, ts, canonical(payload)),
        )
        first = self.db.execute(
            "SELECT ts,payload FROM ee_lifecycle WHERE session=? AND mint=? AND kind=?",
            (self.session, mint, kind),
        ).fetchone()
        self.benchmark(mint, kind, first["ts"], json.loads(first["payload"]))

    def quality(self, payload, now=None):
        self.assert_integrity()
        self.db.execute(
            "INSERT INTO ee_quality(session,ts,payload) VALUES(?,?,?)",
            (self.session, time.time() if now is None else now, canonical(payload)),
        )
        self.db.commit()

    def close(self, now=None):
        now = time.time() if now is None else now
        self.assert_integrity()
        for row in list(self.db.execute("SELECT * FROM ee_pending")):
            self.unavailable(
                row["signal"],
                json.loads(row["payload"]),
                "UNAVAILABLE_INFRASTRUCTURE",
                "SESSION_STOP_OR_INTERRUPTION",
                now,
            )
        if self.session:
            self.db.execute("UPDATE ee_sessions SET ended=? WHERE id=?", (now, self.session))
        self.db.commit()
        self.db.close()


def result_costs(plan, entry, exit_quote, unit, observation):
    cost = plan["cost_model"]
    entry_total = entry["quote_raw"] * entry["unit_usd"]
    entry_fees = entry["protocol_fees_raw"] * entry["unit_usd"]
    gross_exit = exit_quote["gross_quote_raw"] * unit
    exit_fees = exit_quote["protocol_fees_raw"] * unit
    net_exit = exit_quote["quote_raw"] * unit
    fixed = cost["network_usd_per_side"] + cost["priority_usd_per_side"] + cost["failed_tx_reserve_usd"] / 2
    extra_entry = fixed + entry_total * (cost["platform_pct"] + cost["additional_slippage_pct"]) / 100
    extra_exit = (
        fixed
        + net_exit * (cost["platform_pct"] + cost["additional_slippage_pct"]) / 100
        + cost["account_close_network_usd"]
        + cost["account_close_priority_usd"]
    )
    total_cost = entry_fees + exit_fees + extra_entry + extra_exit
    if not all(math.isfinite(v) and v >= 0 for v in (unit, entry_total, gross_exit, net_exit, total_cost)):
        raise QuoteUnavailable()
    gross_pnl = gross_exit + entry["cash_left_usd"] + entry_fees - 4
    net_pnl = net_exit + entry["cash_left_usd"] - 4 - extra_entry - extra_exit
    return dict(
        gross_proceeds_usd=gross_exit,
        net_proceeds_usd=net_exit,
        entry_cost_usd=entry_fees + extra_entry,
        exit_cost_usd=exit_fees + extra_exit,
        total_cost_usd=total_cost,
        gross_return_pct=100 * gross_pnl / 4,
        net_return_pct=100 * net_pnl / 4,
        net_pnl_usd=net_pnl,
        token_quantity=entry["quantity"],
        unused_cash_usd=entry["cash_left_usd"],
        entry_quote_raw=entry["quote_raw"],
        exit_quote_raw=exit_quote["quote_raw"],
        entry_state=entry["state"],
        exit_state=asdict(observation),
        entry_protocol_fee_usd=entry_fees,
        exit_protocol_fee_usd=exit_fees,
        recoverable_rent_capital_usd=entry["rent_usd"],
        upfront_capital_requirement_usd=4 + extra_entry + entry["rent_usd"],
        cost_ledger=[
            dict(
                component="protocol_creator_lp",
                classification="EMBEDDED_IN_AUTHORITATIVE_QUOTE",
                usd=entry_fees + exit_fees,
            ),
            dict(
                component="reserve_price_impact", classification="EMBEDDED_IN_AUTHORITATIVE_QUOTE", usd=None
            ),
            dict(
                component="network_entry_exit_close",
                classification="UNAVOIDABLE_EXTERNAL_COST",
                usd=cost["network_usd_per_side"] * 2 + cost["account_close_network_usd"],
            ),
            dict(
                component="priority_entry_exit_close",
                classification="CONSERVATIVE_EXECUTION_RESERVE",
                usd=cost["priority_usd_per_side"] * 2 + cost["account_close_priority_usd"],
            ),
            dict(
                component="manual_slippage_reserve",
                classification="CONSERVATIVE_EXECUTION_RESERVE",
                usd=(entry_total + net_exit) * cost["additional_slippage_pct"] / 100,
            ),
            dict(
                component="failed_transaction_reserve",
                classification="CONSERVATIVE_EXECUTION_RESERVE",
                usd=cost["failed_tx_reserve_usd"],
            ),
            dict(
                component="interface_platform_assumption",
                classification="CONSERVATIVE_EXECUTION_RESERVE" if cost["platform_pct"] else "NOT_APPLICABLE",
                usd=(entry_total + net_exit) * cost["platform_pct"] / 100,
            ),
            dict(
                component="base_ata_rent", classification="RECOVERABLE_CAPITAL_LOCKUP", usd=entry["rent_usd"]
            ),
        ],
        non_recovery_sensitivity_net_return_pct=100 * (net_pnl - entry["rent_usd"]) / 4,
        protocol_only_net_return_pct=100
        * (
            net_exit
            + entry["cash_left_usd"]
            - 4
            - cost["network_usd_per_side"] * 2
            - cost["account_close_network_usd"]
        )
        / 4,
        cost_policy=cost,
        entry_fee_decomposition_raw=entry.get("fee_decomposition_raw"),
        exit_fee_decomposition_raw=exit_quote.get("fee_decomposition_raw"),
        external_entry_cost_usd=extra_entry,
        external_exit_cost_usd=extra_exit,
        entry_unit_cost_usd=entry_total / entry["quantity"],
        venue_at_entry="PUMP",
        venue_at_exit=observation.data["venue"],
    )
