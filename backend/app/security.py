from collections import defaultdict
from backend.app.providers import TOKEN_PROGRAM, TOKEN_2022

BENIGN_EXTENSIONS = {
    "metadataPointer",
    "tokenMetadata",
    "groupPointer",
    "groupMemberPointer",
    "tokenGroup",
    "tokenGroupMember",
    "immutableOwner",
}
DANGEROUS_EXTENSIONS = {
    "transferFeeConfig",
    "transferHook",
    "permanentDelegate",
    "defaultAccountState",
    "nonTransferable",
    "pausable",
    "pausableConfig",
    "confidentialTransferMint",
    "confidentialTransferFeeConfig",
    "mintCloseAuthority",
    "interestBearingConfig",
    "scaledUiAmountConfig",
    "permissionedBurn",
}


def analyse_security(account, supply, largest, details, creator, excluded, now, mint=None):
    hard, warnings, observations = [], [], []
    quality = "VERIFIED"
    if not account or not supply:
        return {
            "data_quality": "UNKNOWN",
            "risk_score": 100,
            "hard_failures": [],
            "warnings": ["Missing mint/supply data"],
            "last_updated": now,
        }
    program = account.get("owner", "")
    if program not in [TOKEN_PROGRAM, TOKEN_2022]:
        hard.append("Unexpected token program")
    info = account.get("data", {}).get("parsed", {}).get("info", {})
    if not info or account.get("data", {}).get("parsed", {}).get("type") != "mint":
        quality = "UNKNOWN"
        warnings.append("Mint parser unavailable")
    for authority in ["mintAuthority", "freezeAuthority"]:
        if authority not in info:
            quality = "UNKNOWN"
            warnings.append(f"Missing authority field: {authority}")
        if info.get(authority):
            hard.append(f"Active {authority}")
    extensions = info.get("extensions", [])
    if program == TOKEN_2022 and "extensions" not in info and account.get("space", 82) > 82:
        quality = "UNKNOWN"
        warnings.append("Token-2022 extensions not parsed")
    if program == TOKEN_2022:
        observations.append("Token-2022 is not inherently malicious")
        for ext in extensions:
            name = ext.get("extension", "unknown")
            if name in DANGEROUS_EXTENSIONS:
                hard.append(f"Transfer/authority behaviour requires review: {name}")
            elif name not in BENIGN_EXTENSIONS:
                quality = "UNKNOWN"
                warnings.append(f"Unrecognized extension: {name}")
            else:
                observations.append(f"Metadata/account extension: {name}")
    total = int(supply.get("amount", 0))
    if total <= 0:
        quality = "UNKNOWN"
        warnings.append("Invalid supply")
    balances: dict[str, int] = defaultdict(int)
    excluded_total = 0
    if len(details) != len(largest):
        quality = "UNKNOWN"
        warnings.append("Incomplete holder account data")
    for item, detail in zip(largest, details):
        parsed = (detail or {}).get("data", {}).get("parsed", {}).get("info", {})
        owner = parsed.get("owner")
        if (mint is not None and parsed.get("mint") != mint) or not owner:
            quality = "UNKNOWN"
            warnings.append("Holder ownership unavailable")
            continue
        amount = int(item.get("amount", 0))
        if item["address"] in excluded or owner in excluded:
            excluded_total += amount
            continue
        balances[owner] += amount
    percentages = sorted((100 * v / total for v in balances.values()), reverse=True) if total else []
    creator_pct = 100 * balances.get(creator, 0) / total if total and creator else None
    if not creator:
        warnings.append("Creator identity unavailable")
    observations.append("Top 20 accounts only; unobserved tail is not a full holder census")
    if not excluded_total:
        warnings.append("No verified curve/LP exclusion found; pool ownership may be incomplete")
        quality = "PARTIAL" if quality == "VERIFIED" else quality
    score = min(100, len(hard) * 35 + len(warnings) * 10 + sum(percentages[:5]))
    return {
        "overall_risk": "CRITICAL" if hard else ("UNKNOWN" if quality != "VERIFIED" else "SCREENED"),
        "risk_score": round(score, 1),
        "hard_failures": hard,
        "warnings": warnings,
        "observations": observations,
        "data_quality": quality,
        "last_updated": now,
        "token_program": program,
        "extensions": [
            {
                "extension": e.get("extension", "unknown"),
                "state": e.get("state", {}) if e.get("extension") in DANGEROUS_EXTENSIONS else {},
            }
            for e in extensions
        ],
        "supply_raw": str(total),
        "top_1_independent_pct": percentages[0] if percentages else None,
        "top_5_independent_pct": sum(percentages[:5]) if percentages else None,
        "top_10_independent_pct": sum(percentages[:10]) if percentages else None,
        "creator_pct": creator_pct,
        "excluded_supply_pct": 100 * excluded_total / total if total else None,
        "holder_concentration_score": round(min(100, sum(percentages[:5])), 1),
    }
