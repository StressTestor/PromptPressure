"""
PromptPressure OpenAI Adapter v1.4

Handles API calls to OpenAI for LLM completion.
"""

import os
import requests
import time

def generate_response(prompt, model_name="gpt-4-1106-preview", config=None):
    """
    Generate a response from OpenAI API.
    Args:
        prompt (str): User prompt.
        model_name (str): OpenAI model name.
        config (dict): Optional configuration.
    Returns:
        str: Model-generated response.
    """
    api_key = os.getenv("OPENAI_API_KEY") or (config.get("openai_api_key") if config else None)
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY in environment or config.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7
    }
    endpoint = config.get("openai_endpoint", "https://api.openai.com/v1/chat/completions") if config else "https://api.openai.com/v1/chat/completions"
    
    # Add a small delay to avoid rate limiting
    time.sleep(0.5)
    
    response = requests.post(endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
