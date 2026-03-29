import pytest


class TestConfigTierField:
    def test_tier_field_exists_in_schema(self):
        """Settings model should include a tier field."""
        from promptpressure.config import Settings
        schema = Settings.model_json_schema()
        assert "tier" in schema["properties"], "Settings schema missing 'tier' field"

    def test_tier_default_is_quick(self):
        """tier should default to 'quick' when not specified."""
        from promptpressure.config import Settings
        schema = Settings.model_json_schema()
        assert schema["properties"]["tier"]["default"] == "quick"
