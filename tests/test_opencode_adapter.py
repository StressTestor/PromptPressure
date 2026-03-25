"""Tests for the OpenCode CLI adapter."""
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_single_turn():
    """Single-turn prompt sends opencode -p with correct args."""
    from promptpressure.adapters.opencode_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Hello from OpenCode", b"")
    mock_proc.returncode = 0

    with patch("shutil.which", return_value="/usr/bin/opencode"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await generate_response("Say hello", config={})

    assert result == "Hello from OpenCode"
    args = mock_exec.call_args[0]
    assert args[0] == "opencode"
    assert "-p" in args
    assert "Say hello" in args
    assert "-q" in args


@pytest.mark.asyncio
async def test_multi_turn_concatenation():
    """Multi-turn should concatenate conversation history into a single prompt."""
    from promptpressure.adapters.opencode_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Combined response", b"")
    mock_proc.returncode = 0

    messages = [
        {"role": "user", "content": "Turn 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Turn 2"},
    ]

    with patch("shutil.which", return_value="/usr/bin/opencode"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await generate_response("Turn 2", config={}, messages=messages)

    assert result == "Combined response"
    args = mock_exec.call_args[0]
    # The prompt arg should contain concatenated history
    prompt_arg = args[args.index("-p") + 1]
    assert "USER: Turn 1" in prompt_arg
    assert "ASSISTANT: Response 1" in prompt_arg
    assert "USER: Turn 2" in prompt_arg


@pytest.mark.asyncio
async def test_not_installed():
    """Should raise RuntimeError when opencode is not on PATH."""
    from promptpressure.adapters.opencode_adapter import generate_response

    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="OpenCode CLI not found"):
            await generate_response("test", config={})


@pytest.mark.asyncio
async def test_nonzero_exit():
    """Should raise RuntimeError on non-zero exit code."""
    from promptpressure.adapters.opencode_adapter import generate_response

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"something went wrong")
    mock_proc.returncode = 1

    with patch("shutil.which", return_value="/usr/bin/opencode"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="exited 1"):
            await generate_response("test", config={})


def test_adapter_loader():
    """OpenCode adapter should be registered in the loader."""
    from promptpressure.adapters import load_adapter
    adapter = load_adapter("opencode-zen")
    assert callable(adapter)

    adapter2 = load_adapter("opencode")
    assert callable(adapter2)
