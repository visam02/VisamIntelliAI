import os
from openai import OpenAI
import sys

def test_llm():
    print("--- LLM (Groq) Diagnostic ---")
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")

    print(f"Key: {api_key[:10]}...{api_key[-5:] if api_key else 'None'}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")

    if not api_key:
        print("FAIL: No API Key found in environment.")
        return

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        print("Sending test request to Groq...")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'Connection Successful'"}],
            max_tokens=20
        )
        print(f"SUCCESS: {response.choices[0].message.content}")
    except Exception as e:
        print(f"FAIL: LLM Connection error: {e}")

if __name__ == "__main__":
    test_llm()
