import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

print('GROQ_API_KEY exists:', 'GROQ_API_KEY' in os.environ)
print('OPENAI_API_KEY exists:', 'OPENAI_API_KEY' in os.environ)

if 'GROQ_API_KEY' in os.environ:
    print('GROQ_API_KEY length:', len(os.environ['GROQ_API_KEY']))
if 'OPENAI_API_KEY' in os.environ:
    print('OPENAI_API_KEY length:', len(os.environ['OPENAI_API_KEY']))
