from dataclasses import dataclass, field
from collections import deque


@dataclass
class CreatorRiskProfile:
    wallet: str
    launches: deque = field(default_factory=lambda: deque(maxlen=20))
    observed_buy_volume: dict[str, float] = field(default_factory=dict)
    observed_sell_volume: dict[str, float] = field(default_factory=dict)
    first_sell_seconds: float | None = None

    def observe(self, event, token):
        if event.kind == "create":
            if not any(mint == token.mint for mint, _ in self.launches):
                self.launches.append((token.mint, event.ts))
        if event.kind == "trade" and event.wallet == self.wallet:
            if event.side == "buy":
                self.observed_buy_volume[event.currency] = (
                    self.observed_buy_volume.get(event.currency, 0) + event.volume
                )
            elif event.side == "sell":
                self.observed_sell_volume[event.currency] = (
                    self.observed_sell_volume.get(event.currency, 0) + event.volume
                )
                if self.first_sell_seconds is None:
                    self.first_sell_seconds = max(0, event.ts - token.created)

    def report(self, token):
        return {
            "creator_wallet": self.wallet,
            "identity_quality": "PROVIDER_REPORTED",
            "observed_buy_volume": self.observed_buy_volume,
            "observed_sell_volume": self.observed_sell_volume,
            "volume_units": "Provider native quote units; mixed pairs not aggregated as USD",
            "first_sell_seconds": self.first_sell_seconds,
            "recent_observed_launches": list(self.launches),
            "remaining_supply_pct": token.security.get("creator_pct"),
            "limitations": [
                "Only launches/trades observed this session",
                "Creator fee recipient may change",
                "No claim of comprehensive creator history or wallet ownership",
            ],
        }
