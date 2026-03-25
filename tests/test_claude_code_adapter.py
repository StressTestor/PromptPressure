"""Tests for the Claude Code CLI adapter."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_single_turn():
    """Single-turn prompt sends claude -p with correct args."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Hello from Claude", b"")
    mock_proc.returncode = 0

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await generate_response("Say hello", config={})

    assert result == "Hello from Claude"
    args = mock_exec.call_args[0]
    assert args[0] == "claude"
    assert "-p" in args
    assert "Say hello" in args
    assert "--continue" not in args


@pytest.mark.asyncio
async def test_multi_turn_first_message():
    """First turn of multi-turn should not use --continue."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"First response", b"")
    mock_proc.returncode = 0

    messages = [{"role": "user", "content": "Turn 1"}]

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await generate_response("Turn 1", config={}, messages=messages)

    assert result == "First response"
    args = mock_exec.call_args[0]
    assert "--continue" not in args


@pytest.mark.asyncio
async def test_multi_turn_continuation():
    """Subsequent turns should use --continue."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Continued response", b"")
    mock_proc.returncode = 0

    messages = [
        {"role": "user", "content": "Turn 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Turn 2"},
    ]

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await generate_response("Turn 2", config={}, messages=messages)

    assert result == "Continued response"
    args = mock_exec.call_args[0]
    assert "--continue" in args
    assert "Turn 2" in args


@pytest.mark.asyncio
async def test_model_flag():
    """Model name should be passed via --model."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"opus response", b"")
    mock_proc.returncode = 0

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await generate_response("test", model_name="opus", config={})

    args = mock_exec.call_args[0]
    assert "--model" in args
    assert "opus" in args


@pytest.mark.asyncio
async def test_not_installed():
    """Should raise RuntimeError when claude is not on PATH."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Claude Code CLI not found"):
            await generate_response("test", config={})


@pytest.mark.asyncio
async def test_nonzero_exit():
    """Should raise RuntimeError on non-zero exit code."""
    from promptpressure.adapters.claude_code_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"error message")
    mock_proc.returncode = 1

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="exited 1"):
            await generate_response("test", config={})


def test_adapter_loader():
    """Claude Code adapter should be registered in the loader."""
    from promptpressure.adapters import load_adapter
    adapter = load_adapter("claude-code")
    assert callable(adapter)

    adapter2 = load_adapter("claude")
    assert callable(adapter2)
