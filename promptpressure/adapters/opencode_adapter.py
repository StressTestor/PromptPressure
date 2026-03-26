"""
OpenCode CLI adapter for PromptPressure.

Uses `opencode run` for non-interactive evaluation. No API key needed
for free-tier models (opencode/mimo-v2-omni-free, etc).

Install: npm i -g opencode-ai, brew install anomalyco/tap/opencode,
or curl -fsSL https://opencode.ai/install | bash

Single-turn: opencode run "prompt" -m provider/model --format json
Multi-turn:  opencode run "turn" -m model --continue --format json
"""

import asyncio
import json
import shutil
from typing import Optional


def _check_installed():
    if not shutil.which("opencode"):
        raise RuntimeError(
            "OpenCode CLI not found on PATH. "
            "Install via: npm i -g opencode-ai"
        )


def _parse_json_events(raw: str) -> str:
    """Extract text content from opencode JSON event stream."""
    texts = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                if text:
                    texts.append(text)
        except json.JSONDecodeError:
            continue
    return "".join(texts)


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
        model_name: Model in provider/model format (e.g. opencode/mimo-v2-omni-free).
        config: Optional configuration dict.
        messages: Optional message history for multi-turn.

    Returns:
        Model response text from stdout.
    """
    _check_installed()

    timeout = (config or {}).get("timeout", 120)
    model = model_name or (config or {}).get("model", "")

    if messages:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            prompt,
        )
        is_continuation = sum(1 for m in messages if m["role"] == "assistant") > 0

        cmd = ["opencode", "run", last_user, "--format", "json"]
        if model:
            cmd.extend(["-m", model])
        if is_continuation:
            cmd.append("--continue")
    else:
        cmd = ["opencode", "run", prompt, "--format", "json"]
        if model:
            cmd.extend(["-m", model])

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
            f"OpenCode timed out after {timeout}s"
        )

    if proc.returncode != 0:
        err = stderr.decode().strip() if stderr else ""
        out = stdout.decode().strip() if stdout else ""
        detail = err or out or "unknown error"
        raise RuntimeError(f"OpenCode exited {proc.returncode}: {detail[:500]}")

    raw = stdout.decode()
    response = _parse_json_events(raw)
    if not response:
        # Fallback: strip ANSI codes and header lines from plain text output
        import re
        clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).strip()
        lines = [l for l in clean.splitlines() if not l.startswith('>') and l.strip()]
        response = '\n'.join(lines).strip()

    return response
