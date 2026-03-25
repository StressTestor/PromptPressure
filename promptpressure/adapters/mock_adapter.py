
"""Mock adapter for PromptPressure Eval Suite.

Always returns a deterministic placeholder response.
Useful for CI and local sanity-checks without external API calls.
"""


async def generate_response(prompt: str, model_name: str, config: dict | None = None, messages: list | None = None) -> str:
    if messages:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), prompt)
        turn_num = sum(1 for m in messages if m["role"] == "user")
        return (
            f"[MOCK RESPONSE – turn {turn_num}]\n"
            f"Responding to: {last_user[:100]}\n"
            f"(Context: {turn_num} user messages, {sum(1 for m in messages if m['role'] == 'assistant')} assistant messages)"
        )
    return (
        "[SIMULATED RESPONSE – PromptPressure Mock Adapter v1.7]\n\n"
        "This is a mocked reply for testing the evaluation pipeline.\n"
        "Prompt received:\n---\n"
        f"{prompt}\n---\n"
        "(No external API call was made.)"
    )
