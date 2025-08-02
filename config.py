"""
Configuration management for PromptPressure Eval Suite.
Handles loading and validation of configuration with secure secret management.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file if it exists
load_dotenv()


class Settings(BaseSettings):
    """Base settings with common configuration."""
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        env_nested_delimiter='__',
    )

    # Core settings
    adapter: str = Field(..., description="Adapter to use (e.g., 'openai', 'groq', 'lmstudio', 'mock')")
    model: str = Field(..., description="Model identifier")
    model_name: str = Field(..., description="Display name of the model")
    is_simulation: bool = Field(False, description="Whether to run in simulation mode")
    dataset: str = Field(..., description="Path to the evaluation dataset")
    output: str = Field(..., description="Output filename for evaluation results")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")

    # API endpoints
    groq_endpoint: str = Field(
        "https://api.groq.com/openai/v1/chat/completions",
        description="Groq API endpoint"
    )
    openai_endpoint: str = Field(
        "https://api.openai.com/v1/chat/completions",
        description="OpenAI API endpoint"
    )

    # Secrets (loaded from environment variables)
    groq_api_key: Optional[str] = Field(
        None,
        description="Groq API key (from GROQ_API_KEY environment variable or config)"
    )
    openai_api_key: Optional[str] = Field(
        None,
        description="OpenAI API key (from OPENAI_API_KEY environment variable or config)"
    )

    @model_validator(mode='after')
    def validate_required_secrets(self) -> 'Settings':
        """Validate that required secrets are present for the active adapter."""
        # Handle empty strings in config that should fallback to environment variables
        if hasattr(self, 'groq_api_key') and self.groq_api_key == "":
            self.groq_api_key = None
        if hasattr(self, 'openai_api_key') and self.openai_api_key == "":
            self.openai_api_key = None
        
        adapter_lower = self.adapter.lower()
        if adapter_lower == 'groq' and not self.groq_api_key:
            # Try to get from environment if not in config
            env_key = os.getenv("GROQ_API_KEY")
            if env_key:
                self.groq_api_key = env_key
            else:
                raise ValueError("GROQ_API_KEY is required when using the Groq adapter")
        if adapter_lower == 'openai' and not self.openai_api_key:
            # Try to get from environment if not in config
            env_key = os.getenv("OPENAI_API_KEY")
            if env_key:
                self.openai_api_key = env_key
            else:
                raise ValueError("OPENAI_API_KEY is required when using the OpenAI adapter")
        return self


class SettingsWrapper:
    """
    Wrapper class to handle lazy loading of settings.
    This allows us to set the active adapter for validation.
    """
    _instance = None
    _settings = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsWrapper, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_settings(cls, config_path: Optional[str] = None) -> Settings:
        """Get the settings instance, loading from config if not already loaded."""
        if cls._settings is None:
            # Load from YAML if path is provided
            config_dict = {}
            if config_path and Path(config_path).exists():
                import yaml
                with open(config_path, 'r') as f:
                    config_dict = yaml.safe_load(f) or {}
            
            # Create settings instance
            cls._settings = Settings(**config_dict)
        
        return cls._settings


def get_config(config_path: Optional[str] = None) -> Settings:
    """Get the application configuration."""
    return SettingsWrapper.get_settings(config_path)
