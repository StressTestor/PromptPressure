import os
from dotenv import load_dotenv
import requests
import time

# Auto-load environment variables from .env in repo root
dotenv_path = os.path.join(os.path.dirname(__file__), os.pardir, ".env")
load_dotenv(dotenv_path=dotenv_path)

def generate_response(prompt, model_name="llama3-70b-8192", config=None):
    """
    Generate a response from Groq LLM.
    Args:
        prompt (str): User prompt.
        model_name (str): Groq model name.
        config (dict): Optional configuration.
    Returns:
        str: Model-generated response.
    """
    # Prefer config key, fallback to environment
    api_key = (config.get("groq_api_key") if config and "groq_api_key" in config else None) or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Missing GROQ_API_KEY in environment or config.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.get("temperature", 0.7) if config else 0.7
    }
    endpoint = (config.get("groq_endpoint") if config and "groq_endpoint" in config else None) \
           or "https://api.groq.com/openai/v1/chat/completions"
    
    # Add a small delay to avoid rate limiting
    time.sleep(0.5)
    
    response = requests.post(endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
