import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    mode: Literal["DEMO", "OBSERVE", "PAPER", "MANUAL ASSIST"] = "OBSERVE"
    account_usd: float = Field(default=20, gt=0)
    max_position_fraction: float = Field(default=0.2, gt=0, le=0.25)
    max_open_positions: int = Field(default=1, ge=1, le=5)
    max_candidates: int = Field(default=250, ge=1, le=2000)
    max_deep: int = Field(default=25, ge=1, le=100)
    max_events: int = Field(default=500, ge=10, le=2000)
    queue_size: int = Field(default=1000, ge=10, le=10000)
    rss_limit_mb: float = Field(default=700, ge=100)
    db_limit_mb: float = Field(default=1024, ge=1)
    raw_retention_hours: int = Field(default=24, ge=1)
    snapshot_retention_days: int = Field(default=30, ge=1)
    outcome_retention_days: int = Field(default=90, ge=1)
    max_data_age_seconds: float = Field(default=20, gt=0, le=120)
    security_ttl_seconds: float = Field(default=300, gt=0)
    max_top1_pct: float = Field(default=10, gt=0, le=20)
    max_top5_pct: float = Field(default=30, gt=0, le=50)
    min_buyers: int = Field(default=20, ge=10)
    min_maturity: float = Field(default=65, ge=50, le=100)
    min_momentum: float = Field(default=70, ge=50, le=100)
    max_chase: float = Field(default=60, gt=0, le=70)
    min_liquidity_usd: float = Field(default=10000, gt=0)
    max_impact_pct: float = Field(default=1, gt=0, le=2)
    max_slippage_pct: float = Field(default=1, gt=0, le=2)
    min_holdout_samples: int = Field(default=100, ge=30)
    min_edge_pct: float = Field(default=3, gt=0)
    fee_pct_per_side: float = Field(default=1.25, ge=0, le=10)
    platform_fee_pct: float = Field(default=0, ge=0, le=10)
    network_usd_per_side: float = Field(default=0.005, ge=0)
    priority_usd_per_side: float = Field(default=0.005, ge=0)
    failed_tx_reserve_usd: float = Field(default=0.01, ge=0)
    slippage_pct: float = Field(default=0.5, ge=0, le=2)
    fee_verified: str = "2026-10-08"
    latency_ms: int = Field(default=500, ge=250, le=5000)
    stop_loss_pct: float = Field(default=8, gt=0, le=20)
    take_profit_pct: float = Field(default=15, gt=0)
    max_hold_seconds: float = Field(default=300, gt=0)
    post_grad_wait_seconds: float = Field(default=60, ge=30)
    signal_interval_seconds: float = Field(default=30, ge=10)
    horizons: list[int] = [15, 30, 60, 180, 300, 600, 1800]
    trade_stream_enabled: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if self.max_deep > self.max_candidates:
            raise ValueError("deep set exceeds candidate limit")
        if not self.horizons or any(h <= 0 for h in self.horizons):
            raise ValueError("positive outcome horizons required")
        return self


def load_settings() -> Settings:
    path = Path(os.getenv("RADAR_CONFIG", str(ROOT / "config/conservative.yaml")))
    data = yaml.safe_load(path.read_text()) or {}
    data["mode"] = os.getenv("RADAR_MODE", "OBSERVE").upper()
    return Settings(**data)
