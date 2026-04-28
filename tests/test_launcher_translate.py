import pytest

from promptpressure.launcher_translate import (
    launcher_to_settings_dict,
    LauncherRequest,
)


def test_single_dataset_basic():
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="abc-123")

    assert settings["adapter"] == "ollama"
    assert settings["model"] == "llama3.2:1b"
    assert settings["model_name"] == "llama3.2:1b"
    assert settings["dataset"] == "evals_dataset.json"
    assert settings["output"] == "launcher_abc-123.csv"
    assert settings["tier"] == "full"
    assert settings["temperature"] == 0.7


def test_launcher_tier_runs_untagged_datasets():
    """Regression: launcher previously hardcoded tier='quick', which filtered out
    100% of untagged datasets (entries default to tier='full' in tier.py).
    Verify launcher tier choice + filter_by_tier compose correctly so untagged
    data runs end-to-end."""
    from promptpressure.tier import filter_by_tier

    # Simulate evals_tone_sycophancy.json: 45 entries, none tier-tagged
    untagged_entries = [{"id": f"e{i}", "prompt": "x"} for i in range(45)]

    req = LauncherRequest(
        provider="mock",
        model="mock-test",
        eval_set_ids=["evals_tone_sycophancy.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="regression-001")

    filtered, skipped = filter_by_tier(untagged_entries, settings["tier"])
    assert len(filtered) == 45, (
        f"launcher tier='{settings['tier']}' filters untagged data to "
        f"{len(filtered)}/45 — must include untagged entries"
    )
    assert skipped == 0


def test_multi_dataset_uses_first_with_note():
    """v1 takes the first eval set. Multi-set merging is a v2 TODO."""
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json", "evals_tone_sycophancy.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="def-456")

    assert settings["dataset"] == "evals_dataset.json"


def test_provider_normalized_to_adapter_name():
    req = LauncherRequest(
        provider="OpenRouter",
        model="anthropic/claude-3-haiku",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="xyz-789")

    assert settings["adapter"] == "openrouter"


def test_eval_set_ids_required_non_empty():
    with pytest.raises(ValueError):
        LauncherRequest(provider="ollama", model="x", eval_set_ids=[])


def test_dataset_id_path_traversal_rejected():
    """Reject relative paths or absolute paths — eval_set_ids are bare filenames only."""
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["../etc/passwd"],
    )
    with pytest.raises(ValueError, match="must be a bare filename"):
        launcher_to_settings_dict(req, run_id="bad")


def test_dataset_id_must_match_evals_pattern():
    req = LauncherRequest(
        provider="ollama",
        model="llama3.2:1b",
        eval_set_ids=["evals_dataset.json"],
    )
    settings = launcher_to_settings_dict(req, run_id="ok")
    assert settings["dataset"] == "evals_dataset.json"

    # Non-evals_ filenames are rejected at LauncherRequest construction time
    with pytest.raises(ValueError, match="must start with 'evals_'"):
        LauncherRequest(
            provider="ollama",
            model="llama3.2:1b",
            eval_set_ids=["random_other.json"],
        )


def test_launcher_request_rejects_extra_fields():
    """extra=forbid prevents silent field loss from typos or future field additions."""
    with pytest.raises(ValueError):
        LauncherRequest(
            provider="ollama",
            model="x",
            eval_set_ids=["evals_dataset.json"],
            temperature=0.7,  # not a real field — must reject
        )
