
"""Mock adapter for PromptPressure Eval Suite.

Always returns a deterministic placeholder response.
Useful for CI and local sanity‑checks without external API calls.
"""


def generate_response(prompt: str, model_name: str, config: dict | None = None) -> str:
    return (
        "[SIMULATED RESPONSE – PromptPressure Mock Adapter v1.5]\n\n"
        "This is a mocked reply for testing the evaluation pipeline.\n"
        "Prompt received:\n---\n"
        f"{prompt}\n---\n"
        "(No external API call was made.)"
    )
