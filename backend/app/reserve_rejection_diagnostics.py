"""Fixed numeric telemetry only. Never decides whether a reserve state is accepted."""

CONDITIONS = (
    "CURVE_COMPLETE",
    "MAYHEM_MODE",
    "SUPPLY_MISMATCH",
    "NONZERO_DEPTH",
    "NONZERO_POST_COMPLETE_BASE_OUT",
    "NONZERO_POST_COMPLETE_QUOTE_IN",
)
QUOTE_CATEGORIES = ("UNKNOWN", "SOL", "USDC", "UNSUPPORTED_IDENTITY")


def condition_mask(curve, supply):
    # The original predicate runs first. Missing diagnostic fields cannot change its exception.
    fields = (
        "complete",
        "is_mayhem_mode",
        "token_total_supply",
        "depth",
        "post_complete_base_out",
        "post_complete_quote_in",
    )
    if any(type(curve.get(k)) is not (bool if i < 2 else int) for i, k in enumerate(fields)):
        return 0  # Unknown, not a claim that no rejecting conditions were present.
    flags = (
        curve["complete"],
        curve["is_mayhem_mode"],
        supply != curve["token_total_supply"],
        bool(curve["depth"]),
        bool(curve["post_complete_base_out"]),
        bool(curve["post_complete_quote_in"]),
    )
    return sum(1 << i for i, present in enumerate(flags) if present)


class ReserveRejections:
    """64 fixed masks (zero=unknown), four quote categories; old counts stay unclassified."""

    def __init__(self, old, counts):
        self.masks = [0] * 64
        self.state_quotes = [0] * 4
        self.quote_rejections = [0] * 4
        self.invalid_updates = 0
        if old and (not isinstance(old, dict) or old.get("version") != 1):
            self.invalid_updates = 1
            old = None
        if not old:
            self.masks[0] = counts.get("UNSUPPORTED_CURVE_STATE", 0)
            self.state_quotes[0] = self.masks[0]
            self.quote_rejections[0] = counts.get("UNSUPPORTED_QUOTE", 0)
        else:
            # Whitelist exact keys; corrupted/unknown retained telemetry never changes pricing.
            for key, dest in (
                ("condition_masks", self.masks),
                ("state_quote_categories", self.state_quotes),
                ("unsupported_quote_categories", self.quote_rejections),
            ):
                names = tuple(str(i) for i in range(64)) if key == "condition_masks" else QUOTE_CATEGORIES
                source = old.get(key, {})
                for i, name in enumerate(names):
                    value = source.get(name, 0) if isinstance(source, dict) else None
                    if type(value) is int and value >= 0:
                        dest[i] = value
                    else:
                        self.invalid_updates += 1
                if not isinstance(source, dict) or set(source) - set(names):
                    self.invalid_updates += 1
            value = old.get("invalid_updates", 0)
            self.invalid_updates += value if type(value) is int and value >= 0 else 1

    def record(self, reason, detail):
        if reason not in ("UNSUPPORTED_CURVE_STATE", "UNSUPPORTED_QUOTE"):
            return
        mask, quote = 0, 0
        if (
            type(detail) is tuple
            and len(detail) == 2
            and all(type(x) is int for x in detail)
            and 0 <= detail[0] < 64
            and 0 <= detail[1] < 4
        ):
            mask, quote = detail
        elif detail is not None:
            self.invalid_updates += 1
        if reason == "UNSUPPORTED_CURVE_STATE":
            if not mask or quote not in (1, 2):
                mask, quote = 0, 0
            self.masks[mask] += 1
            self.state_quotes[quote] += 1
        else:
            if mask or quote != 3:
                quote = 0
            self.quote_rejections[quote] += 1

    def snapshot(self, counts):
        total = sum(self.masks)
        return dict(
            version=1,
            rejected_state_attempts=total,
            unknown_condition_attempts=self.masks[0],
            multi_condition_attempts=sum(n for mask, n in enumerate(self.masks) if mask.bit_count() > 1),
            condition_counts={
                name: sum(n for mask, n in enumerate(self.masks) if mask & (1 << i))
                for i, name in enumerate(CONDITIONS)
            },
            condition_masks={str(i): n for i, n in enumerate(self.masks)},
            state_quote_categories=dict(zip(QUOTE_CATEGORIES, self.state_quotes)),
            unsupported_quote_categories=dict(zip(QUOTE_CATEGORIES, self.quote_rejections)),
            invalid_updates=self.invalid_updates,
            reconciled=(
                total == counts.get("UNSUPPORTED_CURVE_STATE", 0) == sum(self.state_quotes)
                and sum(self.quote_rejections) == counts.get("UNSUPPORTED_QUOTE", 0)
            ),
        )
