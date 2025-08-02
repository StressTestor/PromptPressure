# adapters/__init__.py
"""
Central adapter loader for PromptPressure Eval Suite.
"""
from .groq_adapter import generate_response as groq_generate_response
from .lmstudio_adapter import load_adapter as lmstudio_adapter_loader
from .mock_adapter import generate_response as mock_generate_response
from .openai_adapter import generate_response as openai_generate_response
from .openrouter_adapter import generate_response as openrouter_generate_response


def load_adapter(name):
    """
    Returns the adapter function matching the given name.
    Adapter functions have signature (text:str, config:dict) -> response_or_scores
    """
    name_lower = name.lower()
    if name_lower == "groq":
        return lambda text, config: groq_generate_response(text, config.get("model_name"), config)
    if name_lower == "lmstudio":
        return lmstudio_adapter_loader()
    if name_lower == "mock":
        return lambda text, config: mock_generate_response(text, config.get("model_name"), config)
    if name_lower == "openai":
        return lambda text, config: openai_generate_response(text, config.get("model_name"), config)
    if name_lower == "openrouter":
        return lambda text, config: openrouter_generate_response(text, config.get("model_name"), config)
    raise ValueError(f"Unknown adapter: {name}")
