import json
import pytest
from pathlib import Path
from collections import Counter

# Constants from original script
REQUIRED_KEYS = {"category", "expected_behavior", "eval_criteria", "prompt", "id"}
OPTIONAL_KEYS = {"notes", "subcategory", "tier", "difficulty", "per_turn_expectations"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

VALID_TIERS = {"smoke", "quick", "full", "deep"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

def validate_entry(entry: dict, idx: int) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_KEYS - entry.keys()
    extra = set(entry.keys()) - ALLOWED_KEYS
    if missing:
        errors.append(f"Entry {idx}: missing keys {sorted(missing)}")

    if extra:
        errors.append(f"Entry {idx}: extra keys {sorted(extra)}")

    # Basic sanity: ensure non-empty values for specific keys
    for key in ["category", "expected_behavior", "id"]:
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            errors.append(f"Entry {idx}: '{key}' must be a non-empty string")

    # Prompt can be a string (single-turn) or a list of message dicts (multi-turn)
    prompt = entry.get("prompt")
    if isinstance(prompt, str):
        if not prompt.strip():
            errors.append(f"Entry {idx}: 'prompt' must be a non-empty string")
    elif isinstance(prompt, list):
        if len(prompt) == 0:
            errors.append(f"Entry {idx}: 'prompt' array must not be empty")
        for ti, turn in enumerate(prompt):
            if not isinstance(turn, dict) or "role" not in turn or "content" not in turn:
                errors.append(f"Entry {idx}: 'prompt' turn {ti} must have 'role' and 'content'")
    else:
        errors.append(f"Entry {idx}: 'prompt' must be a string or array of message objects")
    
    # Validate eval_criteria is a dict
    if not isinstance(entry.get("eval_criteria"), dict):
        errors.append(f"Entry {idx}: 'eval_criteria' must be an object/dict")

    # Validate subcategory if present
    subcategory = entry.get("subcategory")
    if subcategory is not None and (not isinstance(subcategory, str) or not subcategory.strip()):
        errors.append(f"Entry {idx}: 'subcategory' must be a non-empty string")

    # Validate tier if present
    tier = entry.get("tier")
    if tier is not None and tier not in VALID_TIERS:
        errors.append(f"Entry {idx}: 'tier' must be one of {sorted(VALID_TIERS)}, got '{tier}'")

    # Validate difficulty if present
    difficulty = entry.get("difficulty")
    if difficulty is not None and difficulty not in VALID_DIFFICULTIES:
        errors.append(f"Entry {idx}: 'difficulty' must be one of {sorted(VALID_DIFFICULTIES)}, got '{difficulty}'")

    # Validate per_turn_expectations if present
    pte = entry.get("per_turn_expectations")
    if pte is not None:
        if not isinstance(pte, list):
            errors.append(f"Entry {idx}: 'per_turn_expectations' must be a list")
        else:
            for ti, item in enumerate(pte):
                if not isinstance(item, dict):
                    errors.append(f"Entry {idx}: 'per_turn_expectations[{ti}]' must be an object")
                elif "turn" not in item or "expected" not in item:
                    errors.append(f"Entry {idx}: 'per_turn_expectations[{ti}]' must have 'turn' and 'expected'")
                elif not isinstance(item["turn"], int):
                    errors.append(f"Entry {idx}: 'per_turn_expectations[{ti}].turn' must be an integer")
                elif not isinstance(item["expected"], str) or not item["expected"].strip():
                    errors.append(f"Entry {idx}: 'per_turn_expectations[{ti}].expected' must be a non-empty string")

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

    def test_validate_entry_with_new_schema_fields(self):
        """New schema fields (tier, subcategory, difficulty, per_turn_expectations) should be accepted."""
        entry = {
            "id": "test-new-schema",
            "category": "Instruction Following",
            "subcategory": "formatting_persistence",
            "tier": "quick",
            "difficulty": "medium",
            "prompt": [
                {"role": "user", "content": "Turn 1"},
                {"role": "user", "content": "Turn 2"}
            ],
            "expected_behavior": "Should maintain format",
            "per_turn_expectations": [
                {"turn": 1, "expected": "follows format instruction"},
                {"turn": 2, "expected": "maintains format despite contradiction"}
            ],
            "eval_criteria": {
                "format_maintained": True
            }
        }
        errors = validate_entry(entry, 0)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_validate_entry_invalid_tier(self):
        entry = {
            "id": "test-bad-tier",
            "category": "Test",
            "prompt": "test",
            "expected_behavior": "test",
            "eval_criteria": {"pass": True},
            "tier": "invalid"
        }
        errors = validate_entry(entry, 0)
        assert any("tier" in e for e in errors)

    def test_validate_entry_invalid_difficulty(self):
        entry = {
            "id": "test-bad-diff",
            "category": "Test",
            "prompt": "test",
            "expected_behavior": "test",
            "eval_criteria": {"pass": True},
            "difficulty": "impossible"
        }
        errors = validate_entry(entry, 0)
        assert any("difficulty" in e for e in errors)

    def test_validate_entry_invalid_subcategory(self):
        entry = {
            "id": "test-bad-subcat",
            "category": "Test",
            "prompt": "test",
            "expected_behavior": "test",
            "eval_criteria": {"pass": True},
            "subcategory": 12345
        }
        errors = validate_entry(entry, 0)
        assert any("subcategory" in e for e in errors)

    def test_validate_entry_invalid_per_turn_expectations(self):
        entry = {
            "id": "test-bad-pte",
            "category": "Test",
            "prompt": [{"role": "user", "content": "turn 1"}],
            "expected_behavior": "test",
            "eval_criteria": {"pass": True},
            "per_turn_expectations": [{"wrong_key": "bad"}]
        }
        errors = validate_entry(entry, 0)
        assert any("per_turn_expectations" in e for e in errors)

    def test_validate_entry_backward_compat_no_new_fields(self):
        """Old-format entries with only the original 5 keys must still validate."""
        entry = {
            "id": "legacy_001",
            "category": "Test",
            "prompt": "old format prompt",
            "expected_behavior": "should work",
            "eval_criteria": {"pass": True}
        }
        errors = validate_entry(entry, 0)
        assert len(errors) == 0, f"Legacy entry should validate: {errors}"
