import pytest
import os
from pathlib import Path
from pydantic import ValidationError
from config import Settings

class TestConfigAdvanced:
    def test_missing_template_dir(self):
        """Test that missing template directory raises ValueError."""
        env = {
            "adapter": "mock",
            "model": "test-model",
            "model_name": "Test Model",
            "dataset": "test_dataset.json",
            "output": "test_output.csv",
            "report_template_dir": "non_existent_dir_12345"
        }
        with pytest.raises(ValidationError) as excinfo:
            Settings(**env)
        
        assert "Report template directory 'non_existent_dir_12345' not found" in str(excinfo.value)

    def test_missing_groq_api_key(self):
        """Test that missing Groq API key raises ValueError when adapter is groq."""
        # Ensure env var is not set
        old_key = os.environ.pop("GROQ_API_KEY", None)
        try:
            env = {
                "adapter": "groq",
                "model": "llama3-8b-8192",
                "model_name": "Llama 3",
                "dataset": "test_dataset.json",
                "output": "test_output.csv",
                "report_template_dir": "templates" # Should exist
            }
            with pytest.raises(ValidationError) as excinfo:
                Settings(**env)
            assert "GROQ_API_KEY is required" in str(excinfo.value)
        finally:
            if old_key:
                os.environ["GROQ_API_KEY"] = old_key

    def test_valid_groq_config(self):
        """Test strict validation passes with key."""
        env = {
            "adapter": "groq", 
            "model": "llama3-8b-8192",
            "model_name": "Llama 3",
            "dataset": "test_dataset.json",
            "output": "test_output.csv",
            "report_template_dir": "templates",
            "groq_api_key": "gsk_fake_key"
        }
        settings = Settings(**env)
        assert settings.groq_api_key == "gsk_fake_key"
