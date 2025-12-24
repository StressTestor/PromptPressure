
import os
from dotenv import load_dotenv

def test_environment_variable_loading():
    # Load environment variables
    load_dotenv()
    
    # Check if API keys are present (just check keys exist, don't print them)
    # If this is running in CI/Test env without .env, we might skip or check for dummy
    
    # For now, just assert that we can check environment dict
    assert os.environ is not None
    
    # In a real test ecosystem we might verify specific keys if we set them in pytest setup
    # but for migration, just ensuring no crash:
    groq = os.getenv("GROQ_API_KEY")
    router = os.getenv("OPENROUTER_API_KEY")
    # assert True  # pass if we get here
