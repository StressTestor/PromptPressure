# Multi-Turn Behavioral Drift Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert PromptPressure from a single-turn eval framework to a multi-turn behavioral drift detection tool with 4-tier run system (smoke/quick/full/deep) and 305 eval sequences across 12 categories.

**Architecture:** Extend the existing async eval runner (`cli.py`) with tier filtering after dataset load, per-turn timeout via `asyncio.wait_for`, and automated per-turn metrics (response_length_ratio). Add `--tier` flag to argparse. Archive 30 adversarial entries. Expand dataset from 220 single-turn to 305 multi-turn entries with tier tags. Add Chart.js per-turn charts to HTML report.

**Tech Stack:** Python 3.14, pytest, pydantic-settings, asyncio, jinja2, Chart.js (CDN)

**Design doc:** `~/.gstack/projects/promptpressure/joesephgrey-main-design-20260326-120000.md`
**Autoplan review:** Same file, sections after line 265. 28 auto-decisions, all approved.

---

## file structure

### modified files

| file | responsibility | what changes |
|------|---------------|--------------|
| `tests/test_dataset_validation.py` | dataset schema validation | add new optional keys, tier/difficulty/per_turn_expectations validation |
| `promptpressure/config.py` | pydantic settings model | add `tier` field with default "quick" |
| `promptpressure/cli.py` | eval runner + CLI | add tier filtering, --tier flag, per-turn metrics, timeout scaling |
| `promptpressure/reporting.py` | report generation | add per-turn metrics to template data |
| `promptpressure/templates/report_default.html` | HTML report template | add Chart.js per-turn charts section |
| `evals_dataset.json` | eval dataset | remove 30 adversarial entries, add tier/subcategory/difficulty/per_turn_expectations to all entries |

### new files

| file | responsibility |
|------|---------------|
| `tests/test_tier_filtering.py` | unit tests for tier filter logic |
| `tests/test_cli_tier.py` | tests for --tier CLI flag parsing |
| `tests/test_per_turn_metrics.py` | tests for response_length_ratio computation |
| `promptpressure/tier.py` | tier constants + filter function (single responsibility) |
| `promptpressure/per_turn_metrics.py` | per-turn metric computation functions |
| `archive/adversarial/refusal_sensitivity.json` | archived refusal sensitivity entries |
| `archive/adversarial/README.md` | usage constraints for archived content |
| `schema.json` | JSON Schema for the entry format |

---

### Task 1: Update Schema Validation (ALLOWED_KEYS)

This MUST be done first. Without it, every new dataset entry fails validation with "extra keys" errors.

**Files:**
- Modify: `tests/test_dataset_validation.py:7-9`

- [ ] **Step 1: Write failing test for new optional keys**

Add this test to the `TestDatasetValidation` class in `tests/test_dataset_validation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py::TestDatasetValidation::test_validate_entry_with_new_schema_fields -v`
Expected: FAIL with "extra keys ['difficulty', 'per_turn_expectations', 'subcategory', 'tier']"

- [ ] **Step 3: Update ALLOWED_KEYS**

In `tests/test_dataset_validation.py`, change lines 7-9 from:

```python
REQUIRED_KEYS = {"category", "expected_behavior", "eval_criteria", "prompt", "id"}
OPTIONAL_KEYS = {"notes"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS
```

to:

```python
REQUIRED_KEYS = {"category", "expected_behavior", "eval_criteria", "prompt", "id"}
OPTIONAL_KEYS = {"notes", "subcategory", "tier", "difficulty", "per_turn_expectations"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

VALID_TIERS = {"smoke", "quick", "full", "deep"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
```

- [ ] **Step 4: Add tier/difficulty/per_turn_expectations validation to validate_entry**

Add this block at the end of `validate_entry()`, before the `return errors` line:

```python
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
```

- [ ] **Step 5: Run all validation tests**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py -v`
Expected: ALL PASS (including the new test from Step 1)

- [ ] **Step 6: Write tests for invalid tier/difficulty values**

Add these tests to the `TestDatasetValidation` class:

```python
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
```

- [ ] **Step 7: Run all tests to confirm**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add tests/test_dataset_validation.py
git commit -m "extend dataset schema validation for multi-turn fields

add tier, subcategory, difficulty, per_turn_expectations to OPTIONAL_KEYS.
validate tier values (smoke/quick/full/deep), difficulty values (easy/medium/hard),
and per_turn_expectations structure ({turn: int, expected: str}).
backward compatible: old entries without new fields still validate."
```

---

### Task 2: Tier Filter Module

Extract tier logic into its own module so both the CLI and tests can use it without importing the full async runner.

**Files:**
- Create: `promptpressure/tier.py`
- Create: `tests/test_tier_filtering.py`

- [ ] **Step 1: Write failing tests for tier filtering**

Create `tests/test_tier_filtering.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_tier_filtering.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'promptpressure.tier'"

- [ ] **Step 3: Implement tier module**

Create `promptpressure/tier.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_tier_filtering.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add promptpressure/tier.py tests/test_tier_filtering.py
git commit -m "add tier filtering module with cumulative semantics

TIER_ORDER = [smoke, quick, full, deep]. filter_by_tier uses index
comparison for cumulative inclusion. entries without tier field
default to 'full'. invalid tier entries are silently excluded."
```

---

### Task 3: Add --tier CLI Flag + Config Field

Wire the tier into argparse and the pydantic Settings model so it flows through the config dict to the runner.

**Files:**
- Modify: `promptpressure/config.py:27-34`
- Modify: `promptpressure/cli.py:562-567` and `cli.py:36-38`
- Create: `tests/test_cli_tier.py`

- [ ] **Step 1: Write failing test for config tier field**

Create `tests/test_cli_tier.py`:

```python
import json
import pytest
from promptpressure.tier import TIER_ORDER


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_cli_tier.py::TestConfigTierField -v`
Expected: FAIL with "KeyError: 'tier'" or assertion error

- [ ] **Step 3: Add tier field to Settings**

In `promptpressure/config.py`, add this line after line 34 (after the `temperature` field):

```python
    # Tier settings
    tier: str = Field("quick", description="Run tier: smoke (<60s CI), quick (<10min), full (~1hr), deep (all)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_cli_tier.py::TestConfigTierField -v`
Expected: ALL PASS

- [ ] **Step 5: Add --tier flag to argparse and wire tier filtering into runner**

In `promptpressure/cli.py`, add these lines after line 567 (`--ci` argument):

```python
    parser.add_argument("--tier", choices=["smoke", "quick", "full", "deep"],
                        default=None, help="Run tier (smoke/quick/full/deep). Default: quick")
    parser.add_argument("--smoke", action="store_true", help="Shortcut for --tier smoke")
    parser.add_argument("--quick", action="store_true", help="Shortcut for --tier quick")
```

Then in `main_async()`, after `args = parser.parse_args()` (line 583), add tier resolution:

```python
    # Resolve tier from flags
    if args.smoke:
        tier_override = "smoke"
    elif args.quick:
        tier_override = "quick"
    elif args.tier:
        tier_override = args.tier
    else:
        tier_override = None  # use config default
```

Then in the config loop (around line 631), after `config_dict = config.model_dump()`, add:

```python
        if tier_override:
            config_dict["tier"] = tier_override
```

Now add the tier filtering to `run_evaluation_suite`. After line 38 (`prompts = json.load(f)`), add:

```python
    # Tier filtering
    from promptpressure.tier import filter_by_tier
    tier = config.get("tier", "quick")
    original_count = len(prompts)
    prompts = filter_by_tier(prompts, tier)
    print(f"Tier '{tier}': {len(prompts)}/{original_count} sequences selected")
```

- [ ] **Step 6: Run all tests**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_cli_tier.py tests/test_tier_filtering.py tests/test_dataset_validation.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add promptpressure/config.py promptpressure/cli.py tests/test_cli_tier.py
git commit -m "add --tier CLI flag and tier filtering to eval runner

--tier smoke|quick|full|deep with --smoke and --quick shortcuts.
defaults to quick via Settings model. tier flows through config dict
to run_evaluation_suite which filters using tier.filter_by_tier."
```

---

### Task 4: Archive Adversarial Content

Move 30 Refusal Sensitivity entries (rs_001-rs_030) from the main dataset to an archive directory.

**Files:**
- Create: `archive/adversarial/refusal_sensitivity.json`
- Create: `archive/adversarial/README.md`
- Modify: `evals_dataset.json`

- [ ] **Step 1: Write a script to extract and archive**

Create a temporary script (don't commit it). Run it interactively:

```python
import json

with open("evals_dataset.json", "r") as f:
    data = json.load(f)

archive = [e for e in data if e.get("category") == "Refusal Sensitivity"]
remaining = [e for e in data if e.get("category") != "Refusal Sensitivity"]

print(f"Archiving {len(archive)} entries, keeping {len(remaining)}")
assert len(archive) == 30, f"Expected 30 Refusal Sensitivity entries, got {len(archive)}"
assert len(remaining) == 190, f"Expected 190 remaining entries, got {len(remaining)}"

import os
os.makedirs("archive/adversarial", exist_ok=True)

with open("archive/adversarial/refusal_sensitivity.json", "w") as f:
    json.dump(archive, f, indent=2)

with open("evals_dataset.json", "w") as f:
    json.dump(remaining, f, indent=2)

print("Done. Archived to archive/adversarial/refusal_sensitivity.json")
```

Run: `cd /Volumes/T7/PromptPressure && python3 -c '<paste the script above>'`

- [ ] **Step 2: Create archive README**

Create `archive/adversarial/README.md`:

```markdown
# archived adversarial eval content

these prompts test refusal sensitivity, how models handle requests that could be
interpreted as requesting harmful content but are actually benign (academic research,
creative writing, historical analysis, etc).

## why archived

hosted API providers may flag or rate-limit accounts that send adversarial-adjacent
prompts at scale. these sequences are preserved for:
- local model testing (ollama, llama.cpp, vLLM)
- testing with explicit provider permission
- red-team exercises with appropriate authorization

## how to run

```bash
promptpressure --dataset archive/adversarial/refusal_sensitivity.json --multi-config config.yaml
```

no special flags needed. the archive is just a dataset file in a different directory.

## contents

30 entries (rs_001 through rs_030). all prompts are completely benign but designed
to test whether models over-refuse legitimate requests.
```

- [ ] **Step 3: Verify the archive is valid**

Run: `cd /Volumes/T7/PromptPressure && python3 -c "import json; d=json.load(open('archive/adversarial/refusal_sensitivity.json')); print(f'{len(d)} entries, IDs: {d[0][\"id\"]} ... {d[-1][\"id\"]}')"`
Expected: `30 entries, IDs: rs_001 ... rs_030`

- [ ] **Step 4: Verify main dataset reduced**

Run: `cd /Volumes/T7/PromptPressure && python3 -c "import json; d=json.load(open('evals_dataset.json')); print(f'{len(d)} entries'); cats={e.get('category','?') for e in d}; print('Categories:', sorted(cats))"`
Expected: `190 entries` and no "Refusal Sensitivity" in categories

- [ ] **Step 5: Run dataset validation test**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py::TestDatasetValidation::test_startups_dataset_schema -v`
Expected: PASS (190 entries, all valid)

- [ ] **Step 6: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add archive/adversarial/refusal_sensitivity.json archive/adversarial/README.md evals_dataset.json
git commit -m "archive 30 refusal sensitivity entries to archive/adversarial/

rs_001 through rs_030 moved out of default dataset. accessible via
--dataset archive/adversarial/refusal_sensitivity.json for local model
testing or authorized red-team exercises. main dataset now 190 entries."
```

---

### Task 5: Per-Turn Metrics Module

Automated per-turn metric computation. Start with `response_length_ratio` only (the one metric that works without LLM calls or embeddings). This gets computed per turn inside the runner and attached to results.

**Files:**
- Create: `promptpressure/per_turn_metrics.py`
- Create: `tests/test_per_turn_metrics.py`
- Modify: `promptpressure/cli.py:252-260` (inside `_process_multi_turn`)

- [ ] **Step 1: Write failing tests**

Create `tests/test_per_turn_metrics.py`:

```python
import pytest
from promptpressure.per_turn_metrics import compute_response_length_ratio, compute_turn_metrics


class TestResponseLengthRatio:
    def test_normal_ratio(self):
        ratio = compute_response_length_ratio("hello", "hello world this is a response")
        assert ratio == pytest.approx(6.0, rel=0.1)

    def test_equal_lengths(self):
        ratio = compute_response_length_ratio("abcde", "fghij")
        assert ratio == pytest.approx(1.0)

    def test_empty_user_message(self):
        ratio = compute_response_length_ratio("", "some response")
        assert ratio == 0.0

    def test_empty_response(self):
        ratio = compute_response_length_ratio("hello", "")
        assert ratio == 0.0

    def test_both_empty(self):
        ratio = compute_response_length_ratio("", "")
        assert ratio == 0.0


class TestComputeTurnMetrics:
    def test_returns_dict_with_length_ratio(self):
        result = compute_turn_metrics("short question", "a much longer detailed response here")
        assert "response_length_ratio" in result
        assert isinstance(result["response_length_ratio"], float)

    def test_turn_number_included(self):
        result = compute_turn_metrics("q", "a", turn_number=3)
        assert result["turn"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_per_turn_metrics.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement per_turn_metrics module**

Create `promptpressure/per_turn_metrics.py`:

```python
"""Automated per-turn behavioral metrics for multi-turn eval sequences.

These metrics are computed without LLM grading calls. They measure
observable response characteristics that indicate behavioral drift.
"""


def compute_response_length_ratio(user_message: str, response: str) -> float:
    """Ratio of response length to user message length.

    Detects terse/verbose drift across turns. A model that starts with
    detailed responses and shrinks to one-liners is drifting.

    Returns 0.0 if either input is empty (avoids division by zero).
    """
    if not user_message or not response:
        return 0.0
    return len(response) / len(user_message)


def compute_turn_metrics(
    user_message: str,
    response: str,
    turn_number: int = 0,
) -> dict:
    """Compute all automated metrics for a single turn.

    Args:
        user_message: the user's input for this turn
        response: the model's response for this turn
        turn_number: 1-indexed turn number in the sequence

    Returns:
        dict with metric values for this turn
    """
    return {
        "turn": turn_number,
        "response_length_ratio": compute_response_length_ratio(user_message, response),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_per_turn_metrics.py -v`
Expected: ALL PASS

- [ ] **Step 5: Wire metrics into _process_multi_turn**

In `promptpressure/cli.py`, add an import at the top of the file (around line 24):

```python
from promptpressure.per_turn_metrics import compute_turn_metrics
```

Then inside `_process_multi_turn`, after the line that appends to `turn_responses` (line 260), add metric computation. Replace the block at lines 253-260:

```python
                # Add assistant response to conversation history
                conversation.append({"role": "assistant", "content": response_text})
                turn_entry = {
                    "turn": turn_idx,
                    "user": turn_content,
                    "assistant": response_text
                }
                if turn_reasoning:
                    turn_entry["reasoning"] = turn_reasoning
                # Compute per-turn behavioral metrics
                turn_entry["metrics"] = compute_turn_metrics(
                    turn_content, response_text, turn_number=turn_idx
                )
                turn_responses.append(turn_entry)
```

Then in the `result_data` dict (around line 296), add per-turn metrics summary:

```python
        # Aggregate per-turn metrics for the sequence
        per_turn_metrics = [tr.get("metrics", {}) for tr in turn_responses if tr.get("metrics")]
```

Add `"per_turn_metrics": per_turn_metrics` to the `result_data` dict after the `"plugin_scores"` key.

- [ ] **Step 6: Run all tests**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/ -v --ignore=tests/test_openrouter.py --ignore=tests/test_ollama_adapter.py`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add promptpressure/per_turn_metrics.py tests/test_per_turn_metrics.py promptpressure/cli.py
git commit -m "add per-turn response_length_ratio metric to multi-turn runner

compute_turn_metrics runs after each turn response. response_length_ratio
detects terse/verbose drift across turns. metrics attached to turn_responses
and aggregated in result_data.per_turn_metrics. no LLM calls needed."
```

---

### Task 6: Per-Turn Timeout + Context Window Warning

Add `asyncio.wait_for` per turn call and a rough token estimation that warns when approaching context limits.

**Files:**
- Modify: `promptpressure/cli.py:239-241` (inside `_process_multi_turn`)

- [ ] **Step 1: Add timeout to adapter call**

In `_process_multi_turn` in `cli.py`, replace line 241:

```python
                response_text = await adapter_fn(turn_content, config, messages=list(conversation))
```

with:

```python
                # Timeout scales with turn count: base_timeout * turn_number
                base_timeout = config.get("timeout", 60)
                turn_timeout = base_timeout * (1 + turn_idx * 0.5)  # grows per turn
                try:
                    response_text = await asyncio.wait_for(
                        adapter_fn(turn_content, config, messages=list(conversation)),
                        timeout=turn_timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Turn {turn_idx} timed out after {turn_timeout:.0f}s")
```

- [ ] **Step 2: Add context window token estimation**

In `_process_multi_turn`, after `conversation.append({"role": "assistant", "content": response_text})` (now around line 257), add:

```python
                # Rough token estimation (chars / 4) for context window warning
                total_chars = sum(len(m["content"]) for m in conversation)
                estimated_tokens = total_chars // 4
                if estimated_tokens > 6000 and turn_idx < len(turns):
                    print(f"  warning: {entry.get('id')} at ~{estimated_tokens} tokens after turn {turn_idx} "
                          f"(may exceed small model context windows)")
```

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py tests/test_tier_filtering.py tests/test_per_turn_metrics.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add promptpressure/cli.py
git commit -m "add per-turn timeout scaling and context window warning

timeout grows with turn number: base * (1 + turn * 0.5). warns when
conversation exceeds ~6000 estimated tokens (may overflow 8k context
models). prevents indefinite hangs on deep tier 20-turn sequences."
```

---

### Task 7: Add Tier Tags + New Fields to Existing Dataset

Add `tier`, `subcategory`, and `difficulty` fields to all 190 remaining entries in `evals_dataset.json`. This is content work, not code. Every entry gets tagged.

**Files:**
- Modify: `evals_dataset.json`

- [ ] **Step 1: Write a tagging script**

Run this script to add default fields to all entries. The existing 25 sycophancy multi-turn sequences get `tier: "quick"` (3 of them) and `tier: "full"` (22 of them). All single-turn entries get `tier: "full"`. Difficulty defaults to `medium`.

```python
import json

with open("evals_dataset.json", "r") as f:
    data = json.load(f)

# Tag every entry with defaults
quick_syc = ["sy_001", "sy_005", "sy_010"]  # highest-signal sycophancy for quick tier

for entry in data:
    # Add subcategory if missing (default to "general")
    if "subcategory" not in entry:
        entry["subcategory"] = "general"

    # Add difficulty if missing
    if "difficulty" not in entry:
        entry["difficulty"] = "medium"

    # Add tier
    if "tier" not in entry:
        if entry["id"] in quick_syc:
            entry["tier"] = "quick"
        else:
            entry["tier"] = "full"

with open("evals_dataset.json", "w") as f:
    json.dump(data, f, indent=2)

# Verify
tier_counts = {}
for e in data:
    t = e.get("tier", "?")
    tier_counts[t] = tier_counts.get(t, 0) + 1
print(f"Tier distribution: {tier_counts}")
print(f"Total: {len(data)}")
```

Run: `cd /Volumes/T7/PromptPressure && python3 -c '<paste script>'`
Expected: `Tier distribution: {'quick': 3, 'full': 187}` and `Total: 190`

- [ ] **Step 2: Run validation**

Run: `cd /Volumes/T7/PromptPressure && python -m pytest tests/test_dataset_validation.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add evals_dataset.json
git commit -m "add tier, subcategory, difficulty fields to all 190 dataset entries

3 sycophancy entries tagged quick tier, 187 tagged full. all entries
get subcategory='general' and difficulty='medium' as defaults. these
get refined as new multi-turn sequences are added in subsequent commits."
```

---

### Task 8: JSON Schema File

Create a machine-readable schema that documents the entry format for contributors and tooling.

**Files:**
- Create: `schema.json`

- [ ] **Step 1: Create schema.json**

Create `schema.json` in the project root:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PromptPressure Eval Dataset",
  "description": "Schema for entries in evals_dataset.json",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "category", "prompt", "expected_behavior", "eval_criteria"],
    "properties": {
      "id": {
        "type": "string",
        "pattern": "^[a-z]{2,4}_\\d{3}$",
        "description": "Unique entry ID, e.g. if_001, sy_025"
      },
      "category": {
        "type": "string",
        "description": "Evaluation category name"
      },
      "subcategory": {
        "type": "string",
        "description": "Subcategory within the category"
      },
      "tier": {
        "type": "string",
        "enum": ["smoke", "quick", "full", "deep"],
        "description": "Run tier. smoke < quick < full < deep (cumulative)"
      },
      "difficulty": {
        "type": "string",
        "enum": ["easy", "medium", "hard"],
        "description": "Difficulty level (orthogonal to tier)"
      },
      "prompt": {
        "oneOf": [
          {"type": "string", "minLength": 1},
          {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["role", "content"],
              "properties": {
                "role": {"type": "string", "enum": ["user", "system", "assistant"]},
                "content": {"type": "string", "minLength": 1}
              }
            }
          }
        ],
        "description": "Single-turn string or multi-turn message array"
      },
      "expected_behavior": {
        "type": "string",
        "minLength": 1,
        "description": "Human-readable description of expected model behavior"
      },
      "per_turn_expectations": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["turn", "expected"],
          "properties": {
            "turn": {"type": "integer", "minimum": 1},
            "expected": {"type": "string", "minLength": 1}
          }
        },
        "description": "Per-turn expected behaviors for multi-turn sequences"
      },
      "eval_criteria": {
        "type": "object",
        "description": "Key-value pairs for LLM-as-judge grading"
      },
      "notes": {
        "type": "string",
        "description": "Optional authoring notes"
      }
    },
    "additionalProperties": false
  }
}
```

- [ ] **Step 2: Validate current dataset against schema**

Run: `cd /Volumes/T7/PromptPressure && pip install jsonschema 2>/dev/null; python3 -c "
import json, jsonschema
schema = json.load(open('schema.json'))
data = json.load(open('evals_dataset.json'))
for i, entry in enumerate(data):
    try:
        jsonschema.validate(entry, schema['items'])
    except jsonschema.ValidationError as e:
        print(f'Entry {i} ({entry.get(\"id\",\"?\")}): {e.message}')
print(f'Validated {len(data)} entries')
"`

Expected: `Validated 190 entries` (or a list of fixable errors from the regex pattern)

Note: if the `id` pattern regex is too strict for existing IDs (some might use different formats), relax the pattern to `"^[a-z_]+\\d{3}$"` or remove the pattern constraint entirely.

- [ ] **Step 3: Commit**

```bash
cd /Volumes/T7/PromptPressure
git add schema.json
git commit -m "add JSON Schema for eval dataset entry format

documents all fields including new tier, subcategory, difficulty, and
per_turn_expectations. validates prompt as either string (single-turn)
or message array (multi-turn). eval_criteria is a flexible object."
```

---

## what's not in this plan (deferred)

These are the content-heavy and chart tasks that build on the infrastructure above. They should be separate plans because each is independently large:

1. **Multi-turn sequence generation** (phases 2+3 from design doc): convert existing categories to multi-turn format, generate 4 new categories. This is 60-130 hours of CC-assisted content work, not code work. Should be its own plan per category.

2. **HTML per-turn charts** (Chart.js integration in `reporting.py` + templates): depends on having actual multi-turn results to chart. Should be done after at least one category is converted and run against a model.

3. **Smoke tier sequence selection**: can only be done after new multi-turn sequences exist. Pick the 5 highest-signal sequences across categories.

4. **README update**: document --tier flag, smoke/quick/full/deep semantics, and the multi-turn drift positioning. Do this after the first multi-model comparison run with the new sequences.

The 8 tasks above give you:
- schema validation that accepts the new format
- tier filtering that works on any dataset
- --tier CLI flag with smoke/quick shortcuts
- adversarial content safely archived
- per-turn response_length_ratio computed automatically
- per-turn timeout + context window warning
- all 190 existing entries tagged with tier/subcategory/difficulty
- machine-readable JSON Schema for the entry format

Run `promptpressure --tier full --multi-config config.yaml` and it works with the existing dataset. The multi-turn content generation builds on top.
