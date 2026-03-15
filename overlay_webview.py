import webview
import threading
import queue
import os
import ctypes
import json

# ---------------------------------------------------------------------------
# WebViewUI – PyWebView-based overlay with glassmorphism design.
# Replaces overlay_tk.py for a modern look with syntax highlighting.
# ---------------------------------------------------------------------------

class WebViewUI:
    """Modern overlay using PyWebView with JS bridge for thread-safe updates."""

    def __init__(self, trigger_callback, context_callback):
        self.trigger_callback = trigger_callback
        self.context_callback = context_callback
        self._mode = "interview"
        self._code_lang = "python"
        self._collapsed = False
        self._stealth_on = False
        self._window = None
        self._ready = threading.Event()
        self._pending_calls = []  # JS calls queued before webview is ready

    # ── JS API (called from HTML) ───────────────────────────────────────

    class Api:
        def __init__(self, ui):
            self._ui = ui

        def trigger_help(self):
            if self._ui.trigger_callback:
                threading.Thread(target=self._ui.trigger_callback, daemon=True).start()

        def save_settings(self, resume, jd, device_idx, code_lang):
            self._ui._code_lang = code_lang
            device_idx_int = None
            try:
                device_idx_int = int(device_idx)
            except:
                pass
            if self._ui.context_callback:
                self._ui.context_callback(resume, jd, device_idx_int)

        def set_mode(self, mode):
            self._ui._mode = mode
            print(f"[UI] mode switched to: {mode}", flush=True)

        def toggle_collapse(self):
            self._ui._toggle_collapse()

        def close_app(self):
            if self._ui._window:
                self._ui._window.destroy()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def run(self):
        """Start the webview window. Blocks until closed."""
        html_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")

        api = self.Api(self)
        self._window = webview.create_window(
            "VisaMintelli AI",
            url=html_path,
            js_api=api,
            width=420,
            height=600,
            x=500,
            y=180,
            resizable=True,
            frameless=True,
            on_top=True,
            transparent=False,
            background_color="#0f172a",
        )

        self._window.events.loaded += self._on_loaded

        webview.start(debug=False)

    def _on_loaded(self):
        """Called when the HTML page is fully loaded."""
        self._ready.set()
        print("[UI] WebView loaded", flush=True)

        # Enable stealth mode
        self._enable_stealth()

        # Flush any pending JS calls
        for js in self._pending_calls:
            try:
                self._window.evaluate_js(js)
            except:
                pass
        self._pending_calls.clear()

    # ── Thread-safe JS calls ────────────────────────────────────────────

    def _eval_js(self, js_code):
        """Safely evaluate JS in the webview from any thread."""
        if self._ready.is_set() and self._window:
            try:
                self._window.evaluate_js(js_code)
            except Exception as e:
                pass  # Window may be closing
        else:
            self._pending_calls.append(js_code)

    def _escape_js(self, text):
        """Escape text for JS string insertion."""
        return text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("\n", "\\n").replace("\r", "")

    # ── Public update methods (called from any thread) ──────────────────

    def update_status(self, text, state="loading"):
        safe = self._escape_js(text)
        self._eval_js(f'updateStatus(`{safe}`, `{state}`)')

    def update_meter(self, level):
        self._eval_js(f'updateMeter({level:.3f})')

    def append_transcript(self, line):
        safe = self._escape_js(line)
        self._eval_js(f'appendTranscript(`{safe}`)')

    def set_suggestion(self, text):
        safe = self._escape_js(text)
        self._eval_js(f'setSuggestion(formatSuggestion(`{safe}`))')

    def append_suggestion(self, chunk):
        safe = self._escape_js(chunk)
        self._eval_js(f'appendSuggestion(`{safe}`)')

    def clear_suggestion(self):
        self._eval_js('clearSuggestion()')

    def set_streaming(self, active):
        self._eval_js(f'setStreaming({"true" if active else "false"})')

    def set_device_list(self, devices):
        """devices: list of dicts with index and name."""
        js_devs = json.dumps(devices)
        self._eval_js(f'setDeviceList({js_devs})')

    # ── Queue-based update (compatibility with main.py) ─────────────────

    def queue_update(self, action, **kwargs):
        """Compatibility method matching the old TkOverlayUI interface."""
        if action == "status":
            self.update_status(kwargs.get("text", ""), kwargs.get("state", "loading"))
        elif action == "meter":
            self.update_meter(kwargs.get("level", 0))
        elif action == "transcript":
            self.append_transcript(kwargs.get("text", ""))
        elif action == "suggestion_clear":
            self.clear_suggestion()
        elif action == "suggestion_append":
            self.append_suggestion(kwargs.get("chunk", ""))
        elif action == "suggestion_done":
            text = kwargs.get("text", "")
            if text:
                self.set_suggestion(text)
        elif action == "streaming":
            self.set_streaming(kwargs.get("active", False))
        elif action == "device_list":
            self.set_device_list(kwargs.get("devices", []))

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def mode(self):
        return self._mode

    @property
    def code_lang(self):
        return self._code_lang

    # ── Collapse ────────────────────────────────────────────────────────

    def _toggle_collapse(self):
        if not self._window:
            return
        if self._collapsed:
            self._window.resize(420, 600)
            self._collapsed = False
        else:
            self._window.resize(300, 44)
            self._collapsed = True

    # ── Stealth Mode ────────────────────────────────────────────────────

    def _enable_stealth(self):
        """Hide window from screen capture using Windows API."""
        try:
            import ctypes

            # Find the window handle
            hwnd = ctypes.windll.user32.FindWindowW(None, "VisaMintelli AI")
            if not hwnd:
                print("[UI] Stealth: could not find window handle", flush=True)
                return

            # WDA_EXCLUDEFROMCAPTURE = 0x11
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            if result:
                self._stealth_on = True
                print(f"[UI] Stealth ON (HWND={hwnd:#x})", flush=True)
            else:
                # Fallback: WDA_MONITOR = 0x01
                result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x01)
                if result:
                    self._stealth_on = True
                    print(f"[UI] Stealth ON (monitor mode)", flush=True)
                else:
                    err = ctypes.windll.kernel32.GetLastError()
                    print(f"[UI] Stealth failed err={err}", flush=True)
        except Exception as e:
            print(f"[UI] Stealth error: {e}", flush=True)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    def _trigger():
        print("TRIGGER!")

    def _ctx(r, j, d=None):
        print(f"Context: resume={r[:20]}... jd={j[:20]}... dev={d}")

    ui = WebViewUI(_trigger, _ctx)
    ui.run()
