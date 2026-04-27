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
    assert settings["tier"] == "quick"
    assert settings["temperature"] == 0.7


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
