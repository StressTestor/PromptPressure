
"""Dataset schema validator for PromptPressure Eval Suite.

Usage:
    python scripts/validate_dataset.py evals_dataset.json
"""

import json
import sys
from collections import Counter
from pathlib import Path

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


def main(path: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        print(f"✗ Dataset file not found: {path}", file=sys.stderr)

        sys.exit(1)

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"✗ JSON parse error: {exc}", file=sys.stderr)

        sys.exit(1)

    if not isinstance(data, list):
        print("✗ Top‑level JSON must be a list of entries", file=sys.stderr)

        sys.exit(1)

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
        all_errors.append(f"✗ Duplicate ids detected: {len(duplicates)} duplicate id(s)")


    if all_errors:
        print("\n".join(all_errors), file=sys.stderr)

        print(f"\n✗ Validation failed with {len(all_errors)} error(s).", file=sys.stderr)

        sys.exit(1)

    print(f"✓ Dataset {path} is valid — {len(data)} entries, no duplicates.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_dataset.py <dataset_path>", file=sys.stderr)

        sys.exit(1)
    main(sys.argv[1])
