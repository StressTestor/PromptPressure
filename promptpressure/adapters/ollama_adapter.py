"""
Ollama Adapter for PromptPressure
Connects to local Ollama instance for offline LLM inference.
"""
import os
import httpx
from typing import Optional, List, Dict, Any
from promptpressure.rate_limit import AsyncRateLimiter

# Default Ollama endpoint
DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"


async def generate_response(prompt: str, model_name: str = "llama3.2:1b", config: Optional[dict] = None) -> str:
    """
    Generate a response from a local Ollama model.
    
    Args:
        prompt: User prompt.
        model_name: Ollama model name (e.g., "llama3.2:1b", "mistral:7b").
        config: Optional configuration dict.
    
    Returns:
        Model-generated response text.
    """
    endpoint = config.get("ollama_endpoint", DEFAULT_OLLAMA_ENDPOINT) if config else DEFAULT_OLLAMA_ENDPOINT
    temperature = config.get("temperature", 0.7) if config else 0.7
    
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }
    
    # Rate limiting (generous for local)
    await AsyncRateLimiter.wait("ollama", rate=100.0, burst=100.0)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(f"{endpoint}/api/chat", json=data)
        response.raise_for_status()
        result = response.json()
        return result["message"]["content"]


async def list_models(config: Optional[dict] = None) -> List[Dict[str, Any]]:
    """
    List available models from the local Ollama instance.
    
    Returns:
        List of model dictionaries with name, size, etc.
    """
    endpoint = config.get("ollama_endpoint", DEFAULT_OLLAMA_ENDPOINT) if config else DEFAULT_OLLAMA_ENDPOINT
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{endpoint}/api/tags")
        response.raise_for_status()
        result = response.json()
        return result.get("models", [])


async def pull_model(model_name: str, config: Optional[dict] = None) -> bool:
    """
    Pull (download) a model from Ollama registry.
    
    Args:
        model_name: Model to pull (e.g., "llama3.2:1b").
        config: Optional configuration.
    
    Returns:
        True if successful.
    """
    endpoint = config.get("ollama_endpoint", DEFAULT_OLLAMA_ENDPOINT) if config else DEFAULT_OLLAMA_ENDPOINT
    
    async with httpx.AsyncClient(timeout=3600.0) as client:  # Long timeout for large downloads
        response = await client.post(
            f"{endpoint}/api/pull",
            json={"name": model_name, "stream": False}
        )
        response.raise_for_status()
        return True


async def delete_model(model_name: str, config: Optional[dict] = None) -> bool:
    """
    Delete a model from the local Ollama instance.
    
    Args:
        model_name: Model to delete.
        config: Optional configuration.
    
    Returns:
        True if successful.
    """
    endpoint = config.get("ollama_endpoint", DEFAULT_OLLAMA_ENDPOINT) if config else DEFAULT_OLLAMA_ENDPOINT
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{endpoint}/api/delete",
            json={"name": model_name}
        )
        response.raise_for_status()
        return True


async def check_health(config: Optional[dict] = None) -> bool:
    """
    Check if Ollama is running and accessible.
    
    Returns:
        True if Ollama is healthy.
    """
    endpoint = config.get("ollama_endpoint", DEFAULT_OLLAMA_ENDPOINT) if config else DEFAULT_OLLAMA_ENDPOINT
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(endpoint)
            return response.status_code == 200
    except Exception:
        return False
