"""
OpenCode CLI adapter for PromptPressure.

Uses `opencode -p` for non-interactive evaluation. No API key needed —
runs on your OpenCode Zen subscription or configured provider.

Install: npm i -g opencode, brew install opencode, or go install github.com/sst/opencode@latest
"""

import asyncio
import shutil
from typing import Optional


def _check_installed():
    if not shutil.which("opencode"):
        raise RuntimeError(
            "OpenCode CLI not found on PATH. "
            "Install via: npm i -g opencode, brew install opencode, "
            "or go install github.com/sst/opencode@latest"
        )


async def generate_response(
    prompt: str,
    model_name: str = "",
    config: Optional[dict] = None,
    messages: Optional[list] = None,
) -> str:
    """
    Run a prompt through OpenCode's non-interactive mode.

    Args:
        prompt: The prompt text (used for single-turn).
        model_name: Unused (OpenCode selects models via Zen).
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        Model response text from stdout.
    """
    _check_installed()

    timeout = (config or {}).get("timeout", 120)

    if messages:
        # OpenCode doesn't have a --continue flag for multi-turn.
        # Concatenate conversation history into a single prompt.
        parts = []
        for m in messages:
            role = m.get("role", "user").upper()
            parts.append(f"{role}: {m['content']}")
        effective_prompt = "\n\n".join(parts)
    else:
        effective_prompt = prompt

    cmd = ["opencode", "-p", effective_prompt, "-q"]

    # asyncio.create_subprocess_exec does not use a shell — no injection risk
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
            f"OpenCode timed out after {timeout}s"
        )

    if proc.returncode != 0:
        err = stderr.decode().strip() if stderr else "unknown error"
        raise RuntimeError(f"OpenCode exited {proc.returncode}: {err}")

    return stdout.decode().strip()
