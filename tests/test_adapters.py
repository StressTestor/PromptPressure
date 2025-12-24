
import pytest
from adapters import load_adapter

def test_load_mock_adapter():
    adapter = load_adapter("mock")
    assert adapter is not None
    assert callable(adapter)

def test_mock_adapter_response():
    adapter = load_adapter("mock")
    response = adapter("Test prompt", {"is_simulation": True})
    assert "[SIMULATED RESPONSE" in response
    assert "PromptPressure Mock Adapter" in response

def test_load_invalid_adapter():
    with pytest.raises(ValueError):
        load_adapter("nonexistent_adapter")

def test_groq_adapter_loading():
    # Just verify it loads, not calling API without keys
    adapter = load_adapter("groq")
    assert callable(adapter)

def test_lmstudio_adapter_loading():
    adapter = load_adapter("lmstudio")
    assert callable(adapter)
