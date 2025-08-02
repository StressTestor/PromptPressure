# adapters/lmstudio_adapter.py
import requests

def load_adapter(name="lmstudio"):
    """
    Returns a function that sends prompts to an LM Studio endpoint defined in the config.
    """
    def adapter_fn(text, config):
        # Read endpoint and payload settings from config
        endpoint = config.get("lmstudio_endpoint", "http://127.0.0.1:1234/v1/chat/completions")
        payload = {
            "model": config.get("model_name"),
            "messages": [{"role": "user", "content": text}],
            "temperature": config.get("temperature", 0.7),
        }
        # Include optional parameters
        if "max_tokens" in config:
            payload["max_tokens"] = config["max_tokens"]
        # Send request
        resp = requests.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Assume ChatCompletion format
        return data["choices"][0]["message"]["content"]
    return adapter_fn
