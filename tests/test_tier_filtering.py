import pytest
from promptpressure.tier import TIER_ORDER, filter_by_tier


SAMPLE_ENTRIES = [
    {"id": "smoke_1", "tier": "smoke", "prompt": "s1"},
    {"id": "quick_1", "tier": "quick", "prompt": "q1"},
    {"id": "quick_2", "tier": "quick", "prompt": "q2"},
    {"id": "full_1", "tier": "full", "prompt": "f1"},
    {"id": "deep_1", "tier": "deep", "prompt": "d1"},
]


class TestTierOrder:
    def test_order_is_cumulative(self):
        assert TIER_ORDER == ["smoke", "quick", "full", "deep"]


class TestFilterByTier:
    def test_smoke_returns_only_smoke(self):
        result = filter_by_tier(SAMPLE_ENTRIES, "smoke")
        assert [e["id"] for e in result] == ["smoke_1"]

    def test_quick_includes_smoke_and_quick(self):
        result = filter_by_tier(SAMPLE_ENTRIES, "quick")
        ids = {e["id"] for e in result}
        assert ids == {"smoke_1", "quick_1", "quick_2"}

    def test_full_includes_smoke_quick_full(self):
        result = filter_by_tier(SAMPLE_ENTRIES, "full")
        ids = {e["id"] for e in result}
        assert ids == {"smoke_1", "quick_1", "quick_2", "full_1"}

    def test_deep_includes_everything(self):
        result = filter_by_tier(SAMPLE_ENTRIES, "deep")
        assert len(result) == 5

    def test_missing_tier_defaults_to_full(self):
        entries = [{"id": "legacy", "prompt": "no tier field"}]
        assert len(filter_by_tier(entries, "full")) == 1
        assert len(filter_by_tier(entries, "deep")) == 1
        assert len(filter_by_tier(entries, "quick")) == 0
        assert len(filter_by_tier(entries, "smoke")) == 0

    def test_empty_dataset(self):
        assert filter_by_tier([], "quick") == []

    def test_no_matches(self):
        entries = [{"id": "q1", "tier": "quick"}]
        assert filter_by_tier(entries, "smoke") == []

    def test_invalid_tier_in_entry_excluded(self):
        entries = [{"id": "bad", "tier": "invalid"}]
        assert filter_by_tier(entries, "deep") == []

    def test_invalid_requested_tier_raises(self):
        with pytest.raises(ValueError, match="Invalid tier"):
            filter_by_tier(SAMPLE_ENTRIES, "invalid")
