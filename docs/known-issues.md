# known issues

## CostTracker test failures (3 tests, pre-existing)

**tests:**
- `tests/test_batch.py::TestCostTracker::test_record_from_usage`
- `tests/test_batch.py::TestCostTracker::test_multiple_records_accumulate`
- `tests/test_batch.py::TestCostTracker::test_record_from_response_dict`

**symptom:** `KeyError` on `s["per_model"]["test-model"]` — the model key never appears in the cost summary.

**root cause:** `CostTracker.record_from_usage()` and `CostTracker.record()` silently swallow exceptions from `litellm.completion_cost()`. when litellm can't resolve pricing for a test model name (like `"test-model"`), the `except Exception` block increments `requests` but only if the model key already exists in `self.costs`. since the model was never added (the `try` block failed before `self.costs[model]` was created on the first call), the entire record is dropped.

**fix path:** the `if model not in self.costs` init block runs before the `try`, so the key should exist. the actual issue is likely that `litellm.completion_cost()` raises before reaching the `self.costs[model]["requests"] += 1` line, and the model init block is inside the `try`. need to verify — move the init block outside the `try` or add the model to `self.costs` unconditionally before calling `litellm.completion_cost()`.

**severity:** low. cost tracking works in production because real model names resolve in litellm's pricing DB. only affects test fixtures with synthetic model names.

**discovered:** 2026-04-08 during GLM-5.1 integration (confirmed pre-existing on main at `5d3cc10`).
