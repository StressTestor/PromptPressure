"""Tier filtering for PromptPressure eval datasets.

Tiers are cumulative: smoke < quick < full < deep.
--tier quick runs all entries tagged smoke OR quick.
Entries without a tier field default to "full".
"""

TIER_ORDER = ["smoke", "quick", "full", "deep"]


def filter_by_tier(entries: list[dict], tier: str, warn_invalid: bool = False) -> tuple[list[dict], int]:
    """Filter dataset entries by tier level (cumulative).

    Args:
        entries: list of dataset entry dicts
        tier: requested tier level (smoke, quick, full, deep)
        warn_invalid: if True, print warning for entries with invalid tier values

    Returns:
        tuple of (filtered list, count of skipped invalid entries)

    Raises:
        ValueError: if tier is not a valid tier name
    """
    if tier not in TIER_ORDER:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {TIER_ORDER}")

    max_index = TIER_ORDER.index(tier)

    result = []
    skipped = []
    for entry in entries:
        entry_tier = entry.get("tier", "full")
        if entry_tier not in TIER_ORDER:
            skipped.append(entry.get("id", "unknown"))
            continue
        if TIER_ORDER.index(entry_tier) <= max_index:
            result.append(entry)

    if warn_invalid and skipped:
        print(f"  warning: {len(skipped)} entries skipped (invalid tier): {', '.join(skipped[:5])}"
              + (f" and {len(skipped) - 5} more" if len(skipped) > 5 else ""))

    return result, len(skipped)
