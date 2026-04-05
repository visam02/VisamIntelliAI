import sys
import threading
import time
import os

from overlay_webview import WebViewUI
from audio_engine import AudioEngine
from stt_module import STTModule
from llm_module import LLMModule

# ---------------------------------------------------------------------------
# Question detection – scoring-based approach
# ---------------------------------------------------------------------------

QUESTION_STARTERS = [
    "what", "how", "why", "when", "where", "who", "which", "whom",
]

QUESTION_PHRASES = [
    "tell me", "describe", "explain", "can you", "could you",
    "do you", "have you", "are you", "is there", "walk me through",
    "give me", "share", "elaborate", "define", "talk about",
    "what's your", "how do you", "how would you",
]

def question_score(text):
    """Return a confidence score (0-10) that *text* contains a question."""
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

QUESTION_THRESHOLD = 3

# ---------------------------------------------------------------------------
# ParakeetApp – event-driven pipeline with WebView UI
# ---------------------------------------------------------------------------

class ParakeetApp:
    """
    Pipeline:  AudioEngine -> STTModule -> QuestionDetector -> LLMModule -> WebViewUI

    Everything runs on background threads; the UI runs on the main thread.
    All UI mutations go through WebViewUI methods (thread-safe via evaluate_js).
    """

    LLM_COOLDOWN_SEC = 5
    MAX_TRANSCRIPT_LINES = 20

    def __init__(self):
        self._is_thinking = False
        self._last_llm_time = 0
        self._transcript_lines = []
        self._context = {"resume": "", "jd": ""}
        self._shutting_down = False

        # -- UI (main thread) --
        self.ui = WebViewUI(
            trigger_callback=self._on_manual_trigger,
            context_callback=self._on_save_context,
        )

        # -- Backend init on a daemon thread --
        threading.Thread(target=self._init_backend, daemon=True,
                         name="BackendInit").start()

    # -- Backend initialisation ------------------------------------------------

    def _init_backend(self):
        # Wait for UI to be ready
        self.ui._ready.wait(timeout=30)
        time.sleep(0.5)

        try:
            # 1. STT
            self.ui.update_status("Loading speech model...", "loading")
            self.stt = STTModule(result_callback=self._on_transcription)
            self.stt.start()
            self.stt.wait_ready(timeout=60)

            # 2. LLM
            self.ui.update_status("Connecting to LLM...", "loading")
            self.llm = LLMModule()
            if not self.llm.is_ready:
                self.ui.update_status("No API Key", "error")
                print("[main] LLM not ready - set LLM_API_KEY", flush=True)

            # 3. Screen engine (optional)
            self.screen = None
            if not os.environ.get("NO_OCR"):
                try:
                    from screen_engine import ScreenEngine
                    self.screen = ScreenEngine()
                except Exception as e:
                    print(f"[main] screen engine skipped: {e}", flush=True)

            # 4. Audio
            self.ui.update_status("Starting microphone...", "loading")
            source = os.environ.get("AUDIO_SOURCE", "mic")
            self.audio = AudioEngine(
                segment_callback=self._on_audio_segment,
                meter_callback=self._on_meter,
                source=source,
            )
            self.audio.start()

            # Populate UI device list
            devs = AudioEngine.get_devices()
            self.ui.set_device_list(devs)

            # 5. Hotkey (optional)
            try:
                import keyboard
                keyboard.add_hotkey("ctrl+enter", self._on_manual_trigger)
                keyboard.add_hotkey("ctrl+shift+c", self._toggle_coding_mode)
                keyboard.add_hotkey("ctrl+shift+m", self._toggle_meeting_mode)
                print("[main] hotkeys registered: Ctrl+Enter, Ctrl+Shift+C, Ctrl+Shift+M", flush=True)
            except Exception as e:
                print(f"[main] hotkey skipped: {e}", flush=True)

            self.ui.update_status("Listening (auto-detect ON)", "ready")
            print("[main] backend ready OK", flush=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.ui.update_status(f"Init error: {type(e).__name__}", "error")

    # -- Audio callbacks -------------------------------------------------------

    def _on_meter(self, level):
        self.ui.update_meter(level)

    def _on_audio_segment(self, segment):
        if self.stt:
            self.stt.enqueue(segment)

    # -- STT callback ----------------------------------------------------------

    def _on_transcription(self, text):
        if not text or self._shutting_down:
            return
        print(f"[heard] {text}", flush=True)

        self._transcript_lines.append(text)
        if len(self._transcript_lines) > self.MAX_TRANSCRIPT_LINES:
            self._transcript_lines.pop(0)

        self.ui.append_transcript(text)

        # Auto-trigger logic based on mode
        if self.ui.mode == "meeting":
            # Meeting mode: just capture transcript, no auto-trigger
            # User presses Ctrl+Enter for on-demand coaching
            pass
        elif self.ui.mode == "interview":
            # Auto-trigger check (only in interview mode)
            score = question_score(text)
            now = time.time()
            cooldown_ok = (now - self._last_llm_time) > self.LLM_COOLDOWN_SEC
            enough_context = len(self._transcript_lines) >= 2
            if not self._is_thinking and cooldown_ok:
                if score >= QUESTION_THRESHOLD or (enough_context and score >= 2):
                    print(f"[auto-trigger] score={score}", flush=True)
                    self._last_llm_time = now
                    self._request_llm()

    # -- Manual trigger --------------------------------------------------------

    def _on_manual_trigger(self):
        if self._is_thinking:
            return
        self._last_llm_time = time.time()
        self._request_llm()

    # -- Coding mode toggle ----------------------------------------------------

    def _toggle_coding_mode(self):
        new_mode = "interview" if self.ui.mode == "coding" else "coding"
        self.ui._mode = new_mode
        print(f"[main] mode toggled to: {new_mode}", flush=True)

    def _toggle_meeting_mode(self):
        new_mode = "meeting" if self.ui.mode != "meeting" else "interview"
        self.ui._mode = new_mode
        print(f"[main] mode toggled to: {new_mode}", flush=True)

    # -- LLM request -----------------------------------------------------------

    def _request_llm(self):
        if self._is_thinking:
            return
        if not hasattr(self, "llm") or not self.llm.is_ready:
            self.ui.set_suggestion("No API Key. Set LLM_API_KEY env var.")
            return

        transcript = "\n".join(self._transcript_lines)

        # In coding mode, also capture screen if available
        if self.ui.mode == "coding" and self.screen:
            try:
                screen_text = self.screen.get_text()
                if screen_text:
                    transcript = f"[Screen OCR]:\n{screen_text}\n\n[Spoken]:\n{transcript}"
            except Exception as e:
                print(f"[main] screen capture error: {e}", flush=True)

        if not transcript.strip():
            self.ui.set_suggestion("Waiting for input...")
            return

        self._is_thinking = True
        self.ui.update_status("Generating answer...", "loading")
        self.ui.clear_suggestion()
        self.ui.set_streaming(True)

        self.llm.set_context(self._context["resume"], self._context["jd"])

        threading.Thread(target=self._llm_stream_worker, args=(transcript,),
                         daemon=True, name="LLMStream").start()

    def _llm_stream_worker(self, transcript):
        try:
            mode = self.ui.mode
            code_lang = self.ui.code_lang
            for chunk in self.llm.get_suggestion_stream(
                transcript, mode=mode, code_lang=code_lang
            ):
                self.ui.append_suggestion(chunk)
        except Exception as e:
            print(f"[LLM] stream error: {e}", flush=True)
            self.ui.append_suggestion(f"\nError: {e}")
        finally:
            self._is_thinking = False
            self.ui.set_streaming(False)
            self.ui.update_status("Listening (auto-detect ON)", "ready")

    # -- Context save ----------------------------------------------------------

    def _on_save_context(self, resume, jd, device_idx=None):
        self._context["resume"] = resume
        self._context["jd"] = jd
        if hasattr(self, "llm"):
            self.llm.set_context(resume, jd)

        if device_idx is not None and hasattr(self, "audio"):
            if self.audio._device_index != device_idx:
                print(f"[main] switching to audio device {device_idx}", flush=True)
                threading.Thread(target=self.audio.restart, args=(device_idx,),
                                 daemon=True).start()
        print("[main] context/device updated", flush=True)

    # -- Shutdown --------------------------------------------------------------

    def _shutdown(self):
        self._shutting_down = True
        if hasattr(self, "audio"):
            self.audio.stop()
        if hasattr(self, "stt"):
            self.stt.stop()
        print("[main] shutdown complete", flush=True)

    # -- Run -------------------------------------------------------------------

    def run(self):
        try:
            self.ui.run()
        finally:
            self._shutdown()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # If running via pythonw (no console), redirect output to log file
    import sys
    if not sys.stdout or sys.executable.lower().endswith("pythonw.exe"):
        log_path = os.path.join(os.path.dirname(__file__), "visamintelli.log")
        sys.stdout = open(log_path, "w", buffering=1)
        sys.stderr = sys.stdout

    print("=" * 50)
    print("  VisaMintelli AI")
    print("=" * 50)
    print(f"  LLM_API_KEY  = {'set' if os.environ.get('LLM_API_KEY') else 'NOT SET'}")
    print(f"  LLM_BASE_URL = {os.environ.get('LLM_BASE_URL', '(default)')}")
    print(f"  LLM_MODEL    = {os.environ.get('LLM_MODEL', 'gpt-4o')}")
    print(f"  STT_MODEL    = {os.environ.get('STT_MODEL', 'base')}")
    print(f"  AUDIO_SOURCE = {os.environ.get('AUDIO_SOURCE', 'mic')}")
    print("=" * 50)
    app = ParakeetApp()
    app.run()
