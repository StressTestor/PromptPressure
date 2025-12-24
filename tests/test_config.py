
import os
import pytest
from pydantic import ValidationError
from config import Settings

def test_settings_validation_basic():
    # Minimal valid config
    os.environ["GROQ_API_KEY"] = "dummy" # Mock env var if needed by validator
    
    config_dict = {
        "adapter": "mock",
        "model": "test-model",
        "model_name": "Test",
        "dataset": "evals_dataset.json",
        "output": "out.csv",
        "output_dir": "outputs"
    }
    settings = Settings(**config_dict)
    assert settings.adapter == "mock"
    assert settings.temperature == 0.7 # Default

def test_settings_validation_missing_field():
    with pytest.raises(ValidationError):
        Settings(**{"adapter": "mock"}) # Missing many required fields

def test_temperature_range():
    base = {
        "adapter": "mock",
        "model": "test",
        "model_name": "Test",
        "dataset": "d.json",
        "output": "o.csv",
        "output_dir": "o"
    }
    with pytest.raises(ValidationError):
        Settings(**base, temperature=-1.0)
    
    with pytest.raises(ValidationError):
        Settings(**base, temperature=3.0)

