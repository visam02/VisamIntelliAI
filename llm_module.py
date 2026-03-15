import os
from collections import deque

# ---------------------------------------------------------------------------
# LLMModule – interview coach powered by any OpenAI-compatible API.
# Supports streaming responses and keeps short conversation memory.
# ---------------------------------------------------------------------------

class LLMModule:
    """OpenAI-compatible LLM client with streaming and conversation memory."""

    SYSTEM_PROMPT = (
        "You are an expert AI interview coach. The candidate is in a LIVE "
        "interview right now. You can see the recent conversation transcript.\n\n"
        "Rules:\n"
        "• Provide a clear, concise, interview-ready answer.\n"
        "• Format as short bullet points (3-5 bullets max).\n"
        "• Be direct, confident, and professional.\n"
        "• If the candidate's resume/JD context is available, tailor the answer.\n"
        "• Keep the total answer under 120 words.\n"
        "• Do NOT add disclaimers or meta-commentary.\n"
        "• Start immediately with the answer content."
    )

    CODING_PROMPT = (
        "You are an expert coding interview assistant. The candidate is in a LIVE "
        "coding interview. You can see the problem description and any existing code.\n\n"
        "Rules:\n"
        "• Analyze the problem and provide a clean, optimal solution.\n"
        "• Use the specified programming language.\n"
        "• Format code in markdown code blocks with language tag.\n"
        "• Briefly explain the approach (1-2 lines) and time/space complexity.\n"
        "• If you see existing code, suggest improvements or fixes.\n"
        "• Be concise. No disclaimers. Jump straight to the solution.\n"
        "• If the problem is ambiguous, state your assumption in one line."
    )

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL")
        self.model = os.environ.get("LLM_MODEL", "gpt-4o")
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "300"))
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.7"))

        self.client = None
        self._context = ""
        self._memory = deque(maxlen=5)  # last 5 Q&A pairs

        if not self.api_key:
            print("[LLM] WARNING: No API key found. Set LLM_API_KEY env var.", flush=True)
        else:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                print(f"[LLM] client ready  model={self.model}  base_url={self.base_url}", flush=True)
            except Exception as e:
                print(f"[LLM] client init failed: {e}", flush=True)

    # -- public API -----------------------------------------------------------

    def set_context(self, resume_text, job_description):
        parts = []
        if resume_text and resume_text.strip():
            parts.append(f"Resume:\n{resume_text.strip()}")
        if job_description and job_description.strip():
            parts.append(f"Job Description:\n{job_description.strip()}")
        self._context = "\n\n".join(parts)

    @property
    def is_ready(self):
        return self.client is not None

    def get_suggestion(self, transcript):
        """One-shot (non-streaming) response. Returns the full text."""
        if not self.client:
            return "⚠ No API Key. Set LLM_API_KEY environment variable."

        messages = self._build_messages(transcript)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            answer = response.choices[0].message.content.strip()
            self._memory.append({"q": transcript[-200:], "a": answer[:200]})
            return answer
        except Exception as e:
            print(f"[LLM] error: {e}", flush=True)
            return f"⚠ LLM Error: {e}"

    def get_suggestion_stream(self, transcript, mode="interview", code_lang="python"):
        """Generator that yields text chunks as they arrive from the API."""
        if not self.client:
            yield "No API Key. Set LLM_API_KEY environment variable."
            return

        messages = self._build_messages(transcript, mode=mode, code_lang=code_lang)
        full_answer = []

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_answer.append(delta.content)
                    yield delta.content
        except Exception as e:
            print(f"[LLM] stream error: {e}", flush=True)
            yield f"\n⚠ Stream error: {e}"

        # Save to memory
        joined = "".join(full_answer).strip()
        if joined:
            self._memory.append({"q": transcript[-200:], "a": joined[:200]})

    # -- internals ------------------------------------------------------------

    def _build_messages(self, transcript, mode="interview", code_lang="python"):
        prompt = self.CODING_PROMPT if mode == "coding" else self.SYSTEM_PROMPT
        if mode == "coding":
            prompt += f"\n\nPreferred language: {code_lang}"
        messages = [{"role": "system", "content": prompt}]

        # Add conversation memory for continuity
        for pair in self._memory:
            messages.append({"role": "user", "content": f"[Previous Q]: {pair['q']}"})
            messages.append({"role": "assistant", "content": pair["a"]})

        # Build the current user message
        user_parts = []
        if self._context:
            user_parts.append(f"Candidate Context:\n{self._context}")

        if mode == "coding":
            user_parts.append(f"Problem / Screen Content:\n{transcript}")
            user_parts.append("Provide the solution:")
        else:
            user_parts.append(f"Recent Interview Transcript:\n{transcript}")
            user_parts.append("Provide the best answer:")

        messages.append({"role": "user", "content": "\n\n".join(user_parts)})
        return messages


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    llm = LLMModule()
    if llm.is_ready:
        print("--- Streaming test ---")
        for chunk in llm.get_suggestion_stream("Tell me about yourself."):
            print(chunk, end="", flush=True)
        print("\n--- Done ---")
    else:
        print("No API key set. Cannot test.")
