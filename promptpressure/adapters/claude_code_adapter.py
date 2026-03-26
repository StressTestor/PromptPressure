"""
Claude Code CLI adapter for PromptPressure.

Uses `claude -p` for non-interactive evaluation. no API key needed,
runs on your existing Claude Code subscription.

Single-turn: claude -p "<prompt>"
Multi-turn: claude -p "<turn1>" then claude -p "<turn2>" --continue
"""

import asyncio
import shutil
from typing import Optional


def _check_installed():
    if not shutil.which("claude"):
        raise RuntimeError(
            "Claude Code CLI not found on PATH. "
            "Install it: https://docs.anthropic.com/en/docs/claude-code"
        )


async def generate_response(
    prompt: str,
    model_name: str = "",
    config: Optional[dict] = None,
    messages: Optional[list] = None,
) -> str:
    """
    Run a prompt through Claude Code's non-interactive mode.

    Args:
        prompt: The prompt text (used for single-turn).
        model_name: Optional model override (e.g. "sonnet", "opus").
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        Model response text from stdout.
    """
    _check_installed()

    timeout = (config or {}).get("timeout", 120)
    model = model_name or (config or {}).get("model_name", "")

    if messages:
        # Multi-turn: use --continue for turns after the first
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            prompt,
        )
        is_continuation = sum(1 for m in messages if m["role"] == "assistant") > 0

        cmd = ["claude", "-p", last_user, "--no-session-persistence"]
        if is_continuation:
            cmd.append("--continue")
        if model:
            cmd.extend(["--model", model])
    else:
        cmd = ["claude", "-p", prompt, "--no-session-persistence"]
        if model:
            cmd.extend(["--model", model])

    # create_subprocess_exec doesn't use a shell, no injection risk
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(
            f"Claude Code timed out after {timeout}s"
        )

    if proc.returncode != 0:
        err = stderr.decode().strip() if stderr else ""
        out = stdout.decode().strip() if stdout else ""
        detail = err or out or "unknown error"
        raise RuntimeError(f"Claude Code exited {proc.returncode}: {detail[:500]}")

    return stdout.decode().strip()
