"""
Test environment priming.

api.py raises RuntimeError at module import unless either PROMPTPRESSURE_API_SECRET
or PROMPTPRESSURE_DEV_NO_AUTH=1 is set. This conftest sets the dev flag so import works.

Note: the auth gate in api.py is added by a follow-up task. This conftest exists
now so the test infrastructure is in place before any api.py imports land.

Tests verifying the prod auth path should set PROMPTPRESSURE_API_SECRET via
monkeypatch.setenv() and importlib.reload(promptpressure.api) inside the test.
"""
import os

os.environ.setdefault("PROMPTPRESSURE_DEV_NO_AUTH", "1")
