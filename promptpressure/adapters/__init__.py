# adapters/__init__.py
"""
Central adapter loader for PromptPressure Eval Suite.
"""
from .groq_adapter import generate_response as groq_generate_response
from .lmstudio_adapter import load_adapter as lmstudio_adapter_loader
from .mock_adapter import generate_response as mock_generate_response
from .openrouter_adapter import generate_response as openrouter_generate_response
from .ollama_adapter import generate_response as ollama_generate_response
from .claude_code_adapter import generate_response as claude_code_generate_response
from .opencode_adapter import generate_response as opencode_generate_response


def load_adapter(name):
    """
    Returns the adapter function matching the given name.
    Adapter functions have signature:
        async (text:str, config:dict, messages:list|None) -> str
    When messages is provided (multi-turn), text is ignored and
    messages is sent as the full conversation history.
    """
    name_lower = name.lower().replace("-", "_").replace(" ", "_")
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
    if name_lower in ("claude_code", "claude"):
        return lambda text, config, messages=None: claude_code_generate_response(text, config.get("model", ""), config, messages=messages)
    if name_lower in ("opencode_zen", "opencode"):
        return lambda text, config, messages=None: opencode_generate_response(text, config.get("model", ""), config, messages=messages)
    raise ValueError(f"Unknown adapter: {name}")
