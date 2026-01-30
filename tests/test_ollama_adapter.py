"""
Test suite for Ollama adapter.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_ollama_check_health_success():
    """Test Ollama health check when available."""
    from promptpressure.adapters import ollama_adapter
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await ollama_adapter.check_health()
        assert result is True


@pytest.mark.asyncio
async def test_ollama_check_health_failure():
    """Test Ollama health check when unavailable."""
    from promptpressure.adapters import ollama_adapter
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Connection refused")
        
        result = await ollama_adapter.check_health()
        assert result is False


@pytest.mark.asyncio
async def test_ollama_list_models():
    """Test listing Ollama models."""
    from promptpressure.adapters import ollama_adapter
    
    mock_models = {
        "models": [
            {"name": "llama3.2:1b", "size": 1000000},
            {"name": "mistral:7b", "size": 7000000}
        ]
    }
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: mock_models
        mock_response.raise_for_status = lambda: None
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await ollama_adapter.list_models()
        assert len(result) == 2
        assert result[0]["name"] == "llama3.2:1b"


@pytest.mark.asyncio
async def test_ollama_generate_response():
    """Test generating a response via Ollama."""
    from promptpressure.adapters import ollama_adapter
    
    mock_response_data = {
        "message": {
            "content": "Hello! I'm an AI assistant."
        }
    }
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await ollama_adapter.generate_response("Hello", "llama3.2:1b")
        assert "Hello" in result or "AI" in result


def test_adapter_loader_includes_ollama():
    """Test that ollama adapter is registered in the adapter loader."""
    from promptpressure.adapters import load_adapter
    
    adapter = load_adapter("ollama")
    assert adapter is not None
    assert callable(adapter)
