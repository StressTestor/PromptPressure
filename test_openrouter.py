"""
Test script for the OpenRouter adapter.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from adapters import load_adapter
    print("Successfully imported adapters module")
    
    # Try to load the OpenRouter adapter
    adapter = load_adapter("openrouter")
    print("Successfully loaded OpenRouter adapter")
    
    # Test with a simple prompt (this will fail without an API key, but we can verify the function is callable)
    try:
        # This should fail with a ValueError about missing API key
        adapter("Test prompt", {"model_name": "openrouter/horizon-beta"})
        print("ERROR: Expected ValueError for missing API key")
    except ValueError as e:
        if "OPENROUTER_API_KEY" in str(e):
            print("SUCCESS: Correctly identified missing API key")
        else:
            print(f"ERROR: Unexpected ValueError: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        
    print("OpenRouter adapter test completed successfully")
    
except Exception as e:
    print(f"ERROR: Failed to import or load OpenRouter adapter: {e}")
    import traceback
    traceback.print_exc()
