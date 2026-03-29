"""Tier filtering for PromptPressure eval datasets.

Tiers are cumulative: smoke < quick < full < deep.
--tier quick runs all entries tagged smoke OR quick.
Entries without a tier field default to "full".
"""

TIER_ORDER = ["smoke", "quick", "full", "deep"]


def filter_by_tier(entries: list[dict], tier: str) -> list[dict]:
    """Filter dataset entries by tier level (cumulative).

    Args:
        entries: list of dataset entry dicts
        tier: requested tier level (smoke, quick, full, deep)

    Returns:
        filtered list containing entries at or below the requested tier

    Raises:
        ValueError: if tier is not a valid tier name
    """
    if tier not in TIER_ORDER:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {TIER_ORDER}")

    max_index = TIER_ORDER.index(tier)

    result = []
    for entry in entries:
        entry_tier = entry.get("tier", "full")
        if entry_tier not in TIER_ORDER:
            continue  # skip entries with invalid tier values
        if TIER_ORDER.index(entry_tier) <= max_index:
            result.append(entry)
    return result
