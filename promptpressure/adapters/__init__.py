# adapters/__init__.py
"""
Central adapter loader for PromptPressure Eval Suite.
"""
from .groq_adapter import generate_response as groq_generate_response
from .lmstudio_adapter import load_adapter as lmstudio_adapter_loader
from .mock_adapter import generate_response as mock_generate_response
from .openrouter_adapter import generate_response as openrouter_generate_response
from .ollama_adapter import generate_response as ollama_generate_response


def load_adapter(name):
    """
    Returns the adapter function matching the given name.
    Adapter functions have signature:
        async (text:str, config:dict, messages:list|None) -> str
    When messages is provided (multi-turn), text is ignored and
    messages is sent as the full conversation history.
    """
    name_lower = name.lower()
    if name_lower == "groq":
        return lambda text, config, messages=None: groq_generate_response(text, config.get("model_name"), config, messages=messages)
    if name_lower == "lmstudio":
        return lmstudio_adapter_loader()
    if name_lower == "mock":
        return lambda text, config, messages=None: mock_generate_response(text, config.get("model_name"), config, messages=messages)
    if name_lower == "openrouter":
        return lambda text, config, messages=None: openrouter_generate_response(text, config.get("model_name"), config, messages=messages)
    if name_lower == "ollama":
        return lambda text, config, messages=None: ollama_generate_response(text, config.get("model_name"), config, messages=messages)
    raise ValueError(f"Unknown adapter: {name}")
