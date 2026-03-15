"""
VisaMintelli AI – Web Server Mode
Flask + SocketIO server for mobile/cloud deployment.
Phone browser captures mic → server transcribes via Groq → LLM answers → phone shows results.
"""

# eventlet monkey-patching MUST be before all other imports for production WebSocket
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass  # OK for local dev without eventlet

import os
import io
import wave
import time
import struct
import numpy as np
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
from collections import deque

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="ui", template_folder="ui")
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=16 * 1024 * 1024)

# LLM setup
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")

# Groq Whisper for STT
GROQ_API_KEY = LLM_API_KEY  # Same key works for both

# Session state (per-connection)
sessions = {}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("ui", "web.html")

@app.route("/ui/<path:filename>")
def serve_ui(filename):
    return send_from_directory("ui", filename)

# ---------------------------------------------------------------------------
# STT via Groq Whisper
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes):
    """Send audio to Groq Whisper API and return text."""
    try:
        # Browser MediaRecorder sends WebM/Opus – use correct extension
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.webm"

        # Try groq client first, fall back to openai client
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
        except ImportError:
            from openai import OpenAI
            client = OpenAI(api_key=GROQ_API_KEY,
                            base_url="https://api.groq.com/openai/v1")

        t0 = time.time()
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            language="en",
        )
        elapsed = time.time() - t0
        text = result.text.strip() if hasattr(result, 'text') and result.text else str(result).strip()

        # Filter hallucinations
        hallucinations = {"", ".", "you", "thank you.", "thanks.",
                          "Thanks for watching!", "Subscribe"}
        if text.lower().strip(".! ") in {h.lower() for h in hallucinations}:
            return "", elapsed

        print(f"[STT] ({elapsed:.1f}s) {text}", flush=True)
        return text, elapsed
    except Exception as e:
        print(f"[STT] error: {e}", flush=True)
        return "", 0

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def get_llm_stream(transcript, mode="interview", code_lang="python",
                   context="", memory=None):
    """Stream LLM response chunks."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

        if mode == "coding":
            system = (
                "You are an expert coding interview assistant. The candidate is in a LIVE "
                "coding interview.\n\nRules:\n"
                "• Analyze the problem and provide a clean, optimal solution.\n"
                f"• Use {code_lang}.\n"
                "• Format code in markdown code blocks.\n"
                "• Briefly explain approach and complexity.\n"
                "• Be concise. Jump straight to the solution."
            )
        else:
            system = (
                "You are an expert AI interview coach. The candidate is in a LIVE "
                "interview right now.\n\nRules:\n"
                "• Provide a clear, concise, interview-ready answer.\n"
                "• Format as short bullet points (3-5 bullets max).\n"
                "• Be direct, confident, and professional.\n"
                "• Keep under 120 words. Start immediately with the answer."
            )

        messages = [{"role": "system", "content": system}]

        # Add memory
        if memory:
            for pair in memory:
                messages.append({"role": "user", "content": f"[Previous]: {pair['q']}"})
                messages.append({"role": "assistant", "content": pair["a"]})

        user_parts = []
        if context:
            user_parts.append(f"Context:\n{context}")
        user_parts.append(f"Transcript:\n{transcript}")
        user_parts.append("Provide the best answer:")
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        stream = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=400,
            temperature=0.7,
            stream=True,
        )

        full = []
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                full.append(delta.content)
                yield delta.content

        return "".join(full)

    except Exception as e:
        print(f"[LLM] error: {e}", flush=True)
        yield f"\nError: {e}"

# ---------------------------------------------------------------------------
# Question Detection
# ---------------------------------------------------------------------------

QUESTION_STARTERS = ["what", "how", "why", "when", "where", "who", "which"]
QUESTION_PHRASES = ["tell me", "describe", "explain", "can you", "could you",
                     "do you", "have you", "are you", "walk me through",
                     "what's your", "how do you", "how would you"]

def question_score(text):
    lower = text.lower().strip()
    score = 0
    if "?" in text:
        score += 3
    first_word = lower.split()[0] if lower.split() else ""
    if first_word in QUESTION_STARTERS:
        score += 2
    for phrase in QUESTION_PHRASES:
        if phrase in lower:
            score += 1
            break
    if len(lower.split()) >= 4:
        score += 1
    return score

# ---------------------------------------------------------------------------
# SocketIO Events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def handle_connect():
    sid = getattr(emit, '_sid', None) or 'default'
    sessions[sid] = {
        "transcript": deque(maxlen=20),
        "memory": deque(maxlen=5),
        "context": "",
        "mode": "interview",
        "code_lang": "python",
        "last_llm_time": 0,
        "is_thinking": False,
    }
    emit("status", {"text": "Connected", "state": "ready"})
    print(f"[WS] client connected", flush=True)

@socketio.on("disconnect")
def handle_disconnect():
    print(f"[WS] client disconnected", flush=True)

@socketio.on("audio_chunk")
def handle_audio(data):
    """Receive audio bytes from browser, transcribe, auto-trigger LLM."""
    sid = getattr(emit, '_sid', None) or 'default'
    session = sessions.get(sid, sessions.get('default', {}))

    audio_bytes = data.get("audio", b"")
    if not audio_bytes or len(audio_bytes) < 1000:
        return

    # Transcribe
    text, elapsed = transcribe_audio(audio_bytes)
    if not text:
        return

    session.setdefault("transcript", deque(maxlen=20))
    session["transcript"].append(text)
    emit("transcript", {"text": text})

    # Auto-trigger check
    score = question_score(text)
    now = time.time()
    last = session.get("last_llm_time", 0)
    is_thinking = session.get("is_thinking", False)

    if not is_thinking and (now - last) > 5:
        if score >= 3 or (len(session["transcript"]) >= 2 and score >= 2):
            session["last_llm_time"] = now
            session["is_thinking"] = True
            emit("status", {"text": "Generating...", "state": "loading"})
            emit("streaming", {"active": True})
            emit("suggestion_start", {})

            combined = "\n".join(session["transcript"])
            context = session.get("context", "")
            mode = session.get("mode", "interview")
            code_lang = session.get("code_lang", "python")
            memory = list(session.get("memory", []))

            for chunk in get_llm_stream(combined, mode, code_lang, context, memory):
                emit("suggestion_chunk", {"chunk": chunk})

            emit("streaming", {"active": False})
            emit("status", {"text": "Listening", "state": "ready"})
            session["is_thinking"] = False

@socketio.on("trigger_help")
def handle_trigger():
    """Manual trigger from UI."""
    sid = getattr(emit, '_sid', None) or 'default'
    session = sessions.get(sid, sessions.get('default', {}))

    if session.get("is_thinking"):
        return

    session["is_thinking"] = True
    session["last_llm_time"] = time.time()
    emit("status", {"text": "Generating...", "state": "loading"})
    emit("suggestion_start", {})
    emit("streaming", {"active": True})

    combined = "\n".join(session.get("transcript", []))
    if not combined.strip():
        emit("suggestion_chunk", {"chunk": "Waiting for speech..."})
        session["is_thinking"] = False
        emit("streaming", {"active": False})
        return

    context = session.get("context", "")
    mode = session.get("mode", "interview")
    code_lang = session.get("code_lang", "python")
    memory = list(session.get("memory", []))

    for chunk in get_llm_stream(combined, mode, code_lang, context, memory):
        emit("suggestion_chunk", {"chunk": chunk})

    emit("streaming", {"active": False})
    emit("status", {"text": "Listening", "state": "ready"})
    session["is_thinking"] = False

@socketio.on("set_mode")
def handle_mode(data):
    sid = getattr(emit, '_sid', None) or 'default'
    session = sessions.get(sid, sessions.get('default', {}))
    session["mode"] = data.get("mode", "interview")
    print(f"[WS] mode: {session['mode']}", flush=True)

@socketio.on("save_settings")
def handle_settings(data):
    sid = getattr(emit, '_sid', None) or 'default'
    session = sessions.get(sid, sessions.get('default', {}))
    session["context"] = (data.get("resume", "") + "\n" + data.get("jd", "")).strip()
    session["code_lang"] = data.get("code_lang", "python")
    print(f"[WS] settings updated", flush=True)

# ---------------------------------------------------------------------------
# Stealth Mode - pywebview wrapper with screen-capture invisibility
# ---------------------------------------------------------------------------

def _enable_stealth(window_title):
    """Use Windows API to make the window invisible to screen capture."""
    try:
        import ctypes

        # Find the window handle by title
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if not hwnd:
            print(f"[Stealth] Could not find window '{window_title}'", flush=True)
            return False

        # WDA_EXCLUDEFROMCAPTURE = 0x11 (Windows 10 2004+)
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
        if result:
            print(f"[Stealth] ON - window invisible to screen capture (HWND={hwnd:#x})", flush=True)
            return True

        # Fallback: WDA_MONITOR = 0x01 (older Windows 10)
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x01)
        if result:
            print(f"[Stealth] ON - monitor affinity mode (HWND={hwnd:#x})", flush=True)
            return True

        err = ctypes.windll.kernel32.GetLastError()
        print(f"[Stealth] FAILED - err={err}. Try running as Administrator.", flush=True)
        return False
    except Exception as e:
        print(f"[Stealth] Error: {e}", flush=True)
        return False


class StealthApi:
    """JS bridge for pywebview stealth window."""

    def __init__(self):
        self._window = None

    def close_app(self):
        if self._window:
            self._window.destroy()

    def toggle_collapse(self):
        if not self._window:
            return
        w, h = self._window.width, self._window.height
        if h > 60:
            self._window.resize(400, 48)
        else:
            self._window.resize(440, 650)


def run_stealth(port):
    """Launch Flask in background + pywebview stealth window."""
    import webview
    import threading

    # Start Flask server in a background thread
    def start_server():
        socketio.run(app, host="127.0.0.1", port=port, debug=False,
                     allow_unsafe_werkzeug=True, use_reloader=False)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Give server a moment to bind
    time.sleep(0.5)

    api = StealthApi()
    window_title = "VisamIntelliAI"

    window = webview.create_window(
        window_title,
        url=f"http://localhost:{port}",
        js_api=api,
        width=440,
        height=650,
        x=80,
        y=120,
        resizable=True,
        frameless=True,
        on_top=True,
        transparent=False,
        background_color="#0f172a",
    )
    api._window = window

    def on_loaded():
        # Small delay for window to fully render
        time.sleep(0.3)
        _enable_stealth(window_title)
        # Inject stealth-mode flag into the page
        try:
            window.evaluate_js("document.body.classList.add('stealth-mode')")
        except:
            pass

    window.events.loaded += on_loaded
    print(f"[Stealth] Opening invisible overlay -> http://localhost:{port}", flush=True)
    webview.start(debug=False)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VisaMintelli AI Web Server")
    parser.add_argument("--stealth", action="store_true",
                        help="Launch in invisible stealth mode (hidden from screen capture)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)),
                        help="Server port (default: 5000)")
    args = parser.parse_args()

    port = args.port

    print("=" * 50)
    print("  VisaMintelli AI - Web Server")
    print("=" * 50)
    print(f"  Port: {port}")
    print(f"  LLM:  {LLM_MODEL}")
    if args.stealth:
        print("  Mode: STEALTH (invisible to screen capture)")
    else:
        print("  Mode: Normal (open http://localhost:{} in browser)".format(port))
    print("=" * 50)

    if args.stealth:
        run_stealth(port)
    else:
        socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
