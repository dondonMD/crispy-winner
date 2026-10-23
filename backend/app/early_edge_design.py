"""Predeclared manual-entry design. Pure research rules; never strategy rules."""

from backend.app.opportunity import load_intelligence_settings

PRIMARY_LATENCY_MS = 10000
SECONDARY_LATENCIES_MS = (500, 2000, 5000)
LATENCIES_MS = (PRIMARY_LATENCY_MS, *SECONDARY_LATENCIES_MS)
ENTRY_DELAY_SECONDS = 10
TARGET = 100
MAX_DAYS = 30


def readiness(token, now, settings):
    """Same opportunity observation opportunity for both arms; no momentum matching."""
    cfg = load_intelligence_settings()
    points = [(ts, p) for ts, p in token.curve_history if 0 <= now - ts <= 1800]
    verified = (
        token.security.get("data_quality") == "VERIFIED"
        and 0 <= now - token.last_security <= settings.security_ttl_seconds
    )
    n, duration = (3, cfg.progression_min_seconds) if verified else (4, 120)
    coverage = points[-1][0] - points[0][0] if points else 0
    gap = max((b[0] - a[0] for a, b in zip(points, points[1:])), default=0)
    fresh = (
        bool(points)
        and points[-1] == (token.last_curve, token.curve_progress)
        and 0 <= now - token.last_curve <= cfg.curve_fresh_seconds
    )
    return dict(
        ready=bool(fresh and len(points) >= n and coverage >= duration and gap <= cfg.curve_fresh_seconds),
        curve_observation_count=len(points),
        coverage_seconds=coverage,
        largest_observation_gap=gap,
        minimum_observations=n,
        minimum_history_seconds=duration,
        security_verified=verified,
        latest_curve_at=token.last_curve,
        checked_at=now,
    )


def match_key(s, plan):
    p = plan["strata"]
    band = sum(s["curve_progress"] >= x for x in p["progress_edges"])
    age = sum(s["age"] >= x for x in p["age_seconds_edges"])
    return (s["quote_mint"], band, age, s["security_verified"])


def risk_set(treatment, candidates, plan, used=()):
    """Exact timestamp/regime, exact quote/bands/security; deterministic nearest tie break."""
    valid = [
        s
        for s in candidates
        if s
        and s["mint"] != treatment["mint"]
        and s["mint"] not in used
        and s["timestamp"] == treatment["timestamp"]
        and s["action"] != "EARLY_OPPORTUNITY"
        and s.get("observation_readiness", {}).get("ready") is True
        and match_key(s, plan) == match_key(treatment, plan)
    ]
    # Duplicate views of a mint are ambiguous, never pick one by arrival order.
    counts = {s["mint"]: sum(x["mint"] == s["mint"] for x in valid) for s in valid}
    valid = [s for s in valid if counts[s["mint"]] == 1]
    return sorted(
        valid,
        key=lambda s: (
            abs(s["curve_progress"] - treatment["curve_progress"]),
            abs(s["age"] - treatment["age"]),
            s["mint"],
        ),
    )


def design_fields(settings):
    return dict(
        design_version=2,
        primary_position_usd=4,
        primary_latency_seconds=10,
        primary_horizon_seconds=300,
        target_treatment_samples=100,
        max_enrollment_days=30,
        crowd_curve_threshold=85,
        secondary_latency_seconds=[0.5, 2, 5],
        latency_ms=PRIMARY_LATENCY_MS,
        entry_max_delay_seconds=ENTRY_DELAY_SECONDS,
        control="At each treatment T, exact-T risk set; one control, no replacement per mint/session; never enroll generic controls",
        dedup="First EARLY per mint/session; first risk-set selection per control mint/session, no replacement; immutable treatment/control pairs; later crossover cannot rewrite a pair",
        strongest_status_requires="Final closure and primary maturation, 100 numeric treatment outcomes, all treatments matched, all paired controls numeric, zero unavailable, positive mean and paired difference with both bootstrap lower limits >0, valid integrity and independent mint-pair components",
        entry_venue_policy="PUMP pre-grad entry only. Migration before a valid manual fill is unavailable quote, never a guessed PumpSwap buy. Verified PumpSwap state is supported for exits.",
        matching="Exact quote mint/progress band/age band/current verified security; same T market regime; closest progress, closest age, lexical mint. No momentum/persistence matching. Unmatched remain enrolled.",
        observation_readiness=dict(
            verified_min_observations=3,
            verified_min_history_seconds=load_intelligence_settings().progression_min_seconds,
            other_min_observations=4,
            other_min_history_seconds=120,
            lookback_seconds=1800,
            max_gap_seconds=load_intelligence_settings().curve_fresh_seconds,
            latest_max_age_seconds=load_intelligence_settings().curve_fresh_seconds,
            same_floor_both_arms=True,
        ),
        stopping_rule="Close at first 100 unique EARLY mint/session signals or created_at+30 calendar days, earlier. Never extend/restart based on outcomes. Drain declared horizons. Interim counts/quality only.",
        secondary="SECONDARY/EXPLORATORY horizons and .5/2/5s latency variants use the exact same captured prospective state stream; cannot replace 10s/300s primary.",
        analysis="Primary mean at 10s/300s, normal CI and fixed-seed 10000 mint bootstrap. Paired difference resamples mint-connected components closed over immutable matched pairs, preserving crossover and pair dependence.",
        bootstrap_pair_rule="Union mints joined by an immutable pair, including crossovers/sessions; resample whole mint-connected components. Fewer than two independent components: no supporting comparison CI.",
        missingness_policy="Strongest status requires 100 treatment signals with resolved economic primary outcomes, every treatment matched, every paired control resolved, zero unavailable, final closure/maturation and integrity. No automatic economic zero proof rule exists.",
        economic_zero_candidate_rule="DESIGN ONLY, DISABLED: coherent canonical venue/pool/mints/full position quantity; authoritative executable sell quote and verified unavoidable exit-cost schedule at endpoint; prove net recoverable proceeds <=0 without optional reserves, after resolving migration/venue ambiguity. Zero API/dust/missing account is not proof. Archive state/cost proof for review.",
        no_optional_stopping=True,
        no_backfill=True,
        quote_consistency="All pricing accounts from one confirmed getMultipleAccounts context; context >= identity discovery and previous context; complete batch acquired within 5s. Rent separately cached capital requirement, not pricing input.",
        buyer_crowd_marker=dict(
            threshold=settings.min_buyers,
            source="Existing estimated_independent_buyers with CURRENT pre-grad trade evidence; first prospectively observed threshold crossing, no backdating",
            role="SECONDARY_DESCRIPTIVE",
        ),
        parity_requirement="Cohort creation blocked until source/config-bound live diagnostic passes multiple Pump and verified PumpSwap states with exact official SDK comparisons; no unexplained mismatch.",
    )
