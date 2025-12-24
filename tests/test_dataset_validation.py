import json
import pytest
from pathlib import Path
from collections import Counter

# Constants from original script
REQUIRED_KEYS = {"category", "expected_behavior", "eval_criteria", "prompt", "id"}
OPTIONAL_KEYS = {"notes"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

def validate_entry(entry: dict, idx: int) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_KEYS - entry.keys()
    extra = set(entry.keys()) - ALLOWED_KEYS
    if missing:
        errors.append(f"Entry {idx}: missing keys {sorted(missing)}")

    if extra:
        errors.append(f"Entry {idx}: extra keys {sorted(extra)}")

    # Basic sanity: ensure non‑empty string values for specific keys
    for key in ["category", "expected_behavior", "prompt", "id"]:
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            errors.append(f"Entry {idx}: '{key}' must be a non‑empty string")
    
    # Validate eval_criteria is a dict
    if not isinstance(entry.get("eval_criteria"), dict):
        errors.append(f"Entry {idx}: 'eval_criteria' must be an object/dict")

    return errors

def validate_dataset_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"Dataset file not found: {path}"]
    
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON parse error: {exc}"]

    if not isinstance(data, list):
        return ["Top‑level JSON must be a list of entries"]

    all_errors: list[str] = []
    id_counter = Counter()

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            all_errors.append(f"Entry {idx}: must be an object / dict")
            continue
        all_errors.extend(validate_entry(entry, idx))
        id_counter[entry.get("id", "")] += 1

    duplicates = [i for i, cnt in id_counter.items() if i and cnt > 1]
    if duplicates:
        all_errors.append(f"Duplicate ids detected: {len(duplicates)} duplicate id(s)")
        
    return all_errors

class TestDatasetValidation:
    def test_startups_dataset_schema(self):
        """Validates the actual evals_dataset.json file."""
        dataset_path = Path("evals_dataset.json")
        # If the file doesn't exist (e.g. CI/CD without the file), skip or fail depending on reqs.
        # Assuming it should exist in the repo.
        if not dataset_path.exists():
            pytest.skip("evals_dataset.json not found")
        
        errors = validate_dataset_file(dataset_path)
        assert len(errors) == 0, f"Dataset validation failed:\n" + "\n".join(errors)

    def test_validate_entry_valid(self):
        entry = {
            "id": "test-1",
            "category": "security",
            "prompt": "Test prompt",
            "expected_behavior": "Should pass",
            "eval_criteria": {"safe": True}
        }
        errors = validate_entry(entry, 0)
        assert len(errors) == 0

    def test_validate_entry_missing_keys(self):
        entry = {
            "id": "test-2",
            "prompt": "Test"
        }
        errors = validate_entry(entry, 1)
        assert any("missing keys" in e for e in errors)

    def test_validate_entry_extra_keys(self):
        entry = {
            "id": "test-3",
            "category": "security",
            "prompt": "Test prompt",
            "expected_behavior": "Should pass",
            "eval_criteria": {"safe": True},
            "unknown_key": "bad"
        }
        errors = validate_entry(entry, 2)
        assert any("extra keys" in e for e in errors)
