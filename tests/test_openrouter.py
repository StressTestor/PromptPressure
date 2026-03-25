
import pytest
from promptpressure.adapters import load_adapter

def test_openrouter_adapter_loading_and_key_validation():
    # Try to load the OpenRouter adapter
    adapter = load_adapter("openrouter")
    assert callable(adapter)
