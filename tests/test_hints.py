# test_hints.py
from openai import OpenAI

try:
    client = OpenAI()
except Exception:
    client = None

# These model names should show inline cost hints
response = client.chat.completions.create(
    model="gpt-4o", messages=[{"role": "user", "content": "Hello"}]
)

response2 = client.chat.completions.create(
    model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}]
)

response3 = client.chat.completions.create(
    model="claude-3-5-sonnet", messages=[{"role": "user", "content": "Hello"}]
)
