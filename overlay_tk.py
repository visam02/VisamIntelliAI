import tkinter as tk
from tkinter import scrolledtext, font, ttk
import queue
import time

# ---------------------------------------------------------------------------
# TkOverlayUI – always-on-top, frameless overlay for live interview coaching.
# Thread-safe: all external updates go through a queue processed on the main
# thread via _process_queue().
# ---------------------------------------------------------------------------

class TkOverlayUI:
    """Tkinter overlay window with thread-safe update queue."""

    # Color palette
    BG        = "#0f172a"
    CARD      = "#1e293b"
    HEADER_BG = "#1e293b"
    ACCENT    = "#38bdf8"
    GREEN     = "#22c55e"
    RED       = "#ef4444"
    AMBER     = "#f59e0b"
    TEXT      = "#e2e8f0"
    TEXT_DIM  = "#94a3b8"
    TEXT_DARK = "#64748b"
    AI_TEXT   = "#4ade80"
    AI_BG     = "#0d1117"

    def __init__(self, trigger_callback, context_callback):
        self.trigger_callback = trigger_callback
        self.context_callback = context_callback
        self._update_queue = queue.Queue()

        # ── Tkinter root ────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("Parakeet Copilot")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.95)
        self.root.geometry("420x580+500+180")
        self.root.configure(bg=self.BG)

        # ── Hide from screen capture (Windows 10 2004+) ────────────────
        self._stealth_on = False
        self.root.after(100, self._enable_stealth)  # after window is mapped

        # Fonts
        self._font      = font.Font(family="Segoe UI", size=10)
        self._font_bold  = font.Font(family="Segoe UI", size=11, weight="bold")
        self._font_ai    = font.Font(family="Consolas", size=10)
        self._font_small = font.Font(family="Segoe UI", size=8, weight="bold")

        # ── Header bar ─────────────────────────────────────────────────
        self.header = tk.Frame(self.root, bg=self.HEADER_BG, height=36)
        self.header.pack(fill=tk.X)
        self.header.pack_propagate(False)
        self.header.bind("<ButtonPress-1>", self._start_move)
        self.header.bind("<B1-Motion>", self._do_move)

        # Status dot
        self.status_dot = tk.Label(self.header, text="●", fg=self.AMBER,
                                   bg=self.HEADER_BG, font=("Arial", 12))
        self.status_dot.pack(side=tk.LEFT, padx=(10, 4))

        # Status text
        self.status_label = tk.Label(self.header, text="Initializing…",
                                     fg=self.TEXT_DIM, bg=self.HEADER_BG,
                                     font=self._font)
        self.status_label.pack(side=tk.LEFT)

        # Audio level meter
        self.meter_frame = tk.Frame(self.header, bg="#334155", width=50, height=4)
        self.meter_frame.pack(side=tk.LEFT, padx=12)
        self.meter_bar = tk.Frame(self.meter_frame, bg=self.GREEN, width=0, height=4)
        self.meter_bar.place(x=0, y=0)

        # Streaming indicator (blinking dot)
        self._streaming = False
        self._blink_on = False
        self.stream_dot = tk.Label(self.header, text="", fg=self.ACCENT,
                                   bg=self.HEADER_BG, font=("Arial", 10))
        self.stream_dot.pack(side=tk.LEFT, padx=2)

        # ── Header buttons (right side) ────────────────────────────────
        self.close_btn = tk.Button(self.header, text="✕", command=self._on_close,
                                   bg=self.HEADER_BG, fg="#ef4444", borderwidth=0,
                                   font=("Arial", 13), activebackground="#334155")
        self.close_btn.pack(side=tk.RIGHT, padx=(0, 6))

        self.minimize_btn = tk.Button(self.header, text="−", command=self._toggle_collapse,
                                      bg=self.HEADER_BG, fg=self.TEXT_DIM, borderwidth=0,
                                      font=("Arial", 14), activebackground="#334155")
        self.minimize_btn.pack(side=tk.RIGHT, padx=0)

        self.settings_btn = tk.Button(self.header, text="⚙", command=self._toggle_settings,
                                      bg=self.HEADER_BG, fg=self.TEXT_DIM, borderwidth=0,
                                      font=("Arial", 14), activebackground="#334155")
        self.settings_btn.pack(side=tk.RIGHT, padx=0)

        # ── Main content ───────────────────────────────────────────────
        self.content_frame = tk.Frame(self.root, bg=self.BG, padx=12, pady=8)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self._collapsed = False

        # Transcript
        tk.Label(self.content_frame, text="TRANSCRIPT", bg=self.BG,
                 fg=self.TEXT_DARK, font=self._font_small).pack(anchor=tk.W)
        self.transcript_area = scrolledtext.ScrolledText(
            self.content_frame, height=7, bg=self.CARD, fg=self.TEXT,
            borderwidth=0, font=self._font, padx=6, pady=4,
            insertbackground=self.TEXT, wrap=tk.WORD)
        self.transcript_area.pack(fill=tk.X, pady=(2, 8))
        self.transcript_area.config(state=tk.DISABLED)

        # AI Suggestion
        tk.Label(self.content_frame, text="AI SUGGESTION", bg=self.BG,
                 fg=self.GREEN, font=self._font_small).pack(anchor=tk.W)
        self.suggestion_area = scrolledtext.ScrolledText(
            self.content_frame, height=13, bg=self.AI_BG, fg=self.AI_TEXT,
            borderwidth=0, font=self._font_ai, padx=8, pady=6,
            insertbackground=self.AI_TEXT, wrap=tk.WORD)
        self.suggestion_area.pack(fill=tk.X, pady=(2, 10))
        self.suggestion_area.config(state=tk.DISABLED)

        # Help button
        self.help_btn = tk.Button(
            self.content_frame, text="GET AI HELP  (Ctrl+Enter)",
            command=self.trigger_callback,
            bg=self.GREEN, fg="white", font=self._font_bold,
            borderwidth=0, pady=8, activebackground="#16a34a")
        self.help_btn.pack(fill=tk.X)

        # ── Settings overlay (hidden) ──────────────────────────────────
        self.settings_panel = tk.Frame(self.root, bg=self.CARD, padx=15, pady=15)
        self._settings_visible = False

        # --- DEVICE SELECTION ---
        tk.Label(self.settings_panel, text="Audio Input Device", bg=self.CARD, fg=self.TEXT_DIM).pack(anchor=tk.W)
        self.device_var = tk.StringVar(self.root)
        self.device_var.set("Loading devices...")
        self.device_menu = ttk.OptionMenu(self.settings_panel, self.device_var, "Loading...")
        self.device_menu.pack(fill=tk.X, pady=(2, 10))

        # --- CONTEXT ---
        tk.Label(self.settings_panel, text="Resume Context",
                 bg=self.CARD, fg=self.TEXT_DIM).pack(anchor=tk.W)
        self.resume_edit = scrolledtext.ScrolledText(
            self.settings_panel, height=8, bg=self.BG, fg=self.TEXT, borderwidth=0)
        self.resume_edit.pack(fill=tk.X, pady=5)

        tk.Label(self.settings_panel, text="Job Description",
                 bg=self.CARD, fg=self.TEXT_DIM).pack(anchor=tk.W)
        self.jd_edit = scrolledtext.ScrolledText(
            self.settings_panel, height=8, bg=self.BG, fg=self.TEXT, borderwidth=0)
        self.jd_edit.pack(fill=tk.X, pady=5)

        self.save_btn = tk.Button(
            self.settings_panel, text="SAVE CONTEXT",
            command=self._save_settings,
            bg=self.ACCENT, fg="white", font=self._font_bold,
            borderwidth=0, pady=8)
        self.save_btn.pack(fill=tk.X, pady=10)

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        # Start the queue processor
        self._poll_queue()
        self._blink_loop()

    # ── Thread-safe public API ──────────────────────────────────────────

    def queue_update(self, action, **kwargs):
        """Thread-safe: enqueue a UI action to be processed on the main thread."""
        self._update_queue.put((action, kwargs))

    def update_status(self, text, code="ready"):
        """Convenience: update status bar (thread-safe)."""
        self.queue_update("status", text=text, code=code)

    def update_meter(self, level):
        """Convenience: update audio level meter (thread-safe)."""
        self.queue_update("meter", level=level)

    def append_transcript(self, text):
        """Convenience: append text to transcript area (thread-safe)."""
        self.queue_update("transcript", text=text)

    def set_suggestion(self, text):
        """Convenience: replace suggestion area content (thread-safe)."""
        self.queue_update("suggestion_set", text=text)

    def append_suggestion(self, text):
        """Convenience: append chunk to suggestion area — for streaming (thread-safe)."""
        self.queue_update("suggestion_append", text=text)

    def clear_suggestion(self):
        """Convenience: clear suggestion area (thread-safe)."""
        self.queue_update("suggestion_clear")

    def set_streaming(self, active):
        """Show/hide the streaming indicator (thread-safe)."""
        self.queue_update("streaming", active=active)

    # ── Queue processing (main thread) ──────────────────────────────────

    def _poll_queue(self):
        """Process all pending UI updates; reschedule itself every 30 ms."""
        try:
            while True:
                action, kw = self._update_queue.get_nowait()
                self._apply_update(action, kw)
        except queue.Empty:
            pass
        self.root.after(30, self._poll_queue)

    def _apply_update(self, action, kw):
        if action == "status":
            self.status_label.config(text=kw["text"])
            code = kw.get("code", "ready")
            color = {
                "loading": self.AMBER,
                "error": self.RED,
            }.get(code, self.GREEN)
            self.status_dot.config(fg=color)

        elif action == "meter":
            width = int(min(1.0, kw["level"]) * 50)
            self.meter_bar.config(width=max(0, width))

        elif action == "transcript":
            self.transcript_area.config(state=tk.NORMAL)
            self.transcript_area.insert(tk.END, kw["text"] + "\n")
            self.transcript_area.see(tk.END)
            self.transcript_area.config(state=tk.DISABLED)

        elif action == "suggestion_set":
            self.suggestion_area.config(state=tk.NORMAL)
            self.suggestion_area.delete("1.0", tk.END)
            self.suggestion_area.insert(tk.END, kw["text"])
            self.suggestion_area.see(tk.END)
            self.suggestion_area.config(state=tk.DISABLED)

        elif action == "suggestion_append":
            self.suggestion_area.config(state=tk.NORMAL)
            self.suggestion_area.insert(tk.END, kw["text"])
            self.suggestion_area.see(tk.END)
            self.suggestion_area.config(state=tk.DISABLED)

        elif action == "suggestion_clear":
            self.suggestion_area.config(state=tk.NORMAL)
            self.suggestion_area.delete("1.0", tk.END)
            self.suggestion_area.config(state=tk.DISABLED)

        elif action == "streaming":
            self._streaming = kw["active"]

        elif action == "device_list":
            self.set_device_list(kw["devices"])

    # ── Blink loop for streaming indicator ──────────────────────────────

    def _blink_loop(self):
        if self._streaming:
            self._blink_on = not self._blink_on
            self.stream_dot.config(text="●" if self._blink_on else " ")
        else:
            self.stream_dot.config(text="")
            self._blink_on = False
        self.root.after(400, self._blink_loop)

    # ── Stealth mode (invisible to screen capture) ──────────────────────

    def _enable_stealth(self):
        """Use Windows API to hide window from screen capture."""
        try:
            import ctypes
            import ctypes.wintypes

            # For Tkinter with overrideredirect, we need the actual top-level HWND
            # Try multiple approaches to find it
            raw_id = self.root.winfo_id()

            # Approach 1: Walk GetParent chain to find the top-level window
            hwnd = raw_id
            parent = ctypes.windll.user32.GetParent(hwnd)
            while parent:
                hwnd = parent
                parent = ctypes.windll.user32.GetParent(hwnd)

            # Try SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE (0x11)
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            if result:
                self._stealth_on = True
                self._stealth_hwnd = hwnd
                print(f"[UI] Stealth ON (HWND={hwnd:#x}) - invisible to screen capture", flush=True)
                return

            # Approach 2: Try FindWindow
            hwnd2 = ctypes.windll.user32.FindWindowW(None, "Parakeet Copilot")
            if hwnd2:
                result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd2, 0x11)
                if result:
                    self._stealth_on = True
                    self._stealth_hwnd = hwnd2
                    print(f"[UI] Stealth ON via FindWindow (HWND={hwnd2:#x})", flush=True)
                    return

            # Approach 3: Try WDA_MONITOR (0x01) as fallback
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x01)
            if result:
                self._stealth_on = True
                self._stealth_hwnd = hwnd
                print(f"[UI] Stealth ON (monitor affinity fallback)", flush=True)
                return

            err = ctypes.windll.kernel32.GetLastError()
            print(f"[UI] Stealth failed - HWND={hwnd:#x} raw={raw_id:#x} err={err}", flush=True)
            print("[UI] TIP: Try running as Administrator for stealth mode", flush=True)
        except Exception as e:
            print(f"[UI] Stealth setup error: {e}", flush=True)

    def _toggle_stealth(self):
        """Toggle stealth mode on/off."""
        try:
            import ctypes
            hwnd = getattr(self, '_stealth_hwnd', None)
            if not hwnd:
                self._enable_stealth()
                return
            if self._stealth_on:
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00)
                self._stealth_on = False
                print("[UI] Stealth OFF - visible to screen capture", flush=True)
            else:
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
                self._stealth_on = True
                print("[UI] Stealth ON - invisible to screen capture", flush=True)
        except Exception as e:
            print(f"[UI] Stealth toggle failed: {e}", flush=True)

    # ── Window controls ─────────────────────────────────────────────────

    def _start_move(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_move(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    def _toggle_collapse(self):
        if self._collapsed:
            # Expand back
            self.content_frame.pack(fill=tk.BOTH, expand=True)
            self.root.geometry("420x580")
            self.minimize_btn.config(text="−")
            self._collapsed = False
        else:
            # Collapse to a visible strip (not too tiny)
            self.content_frame.pack_forget()
            self.root.geometry("300x40")
            self.minimize_btn.config(text="▲")
            self._collapsed = True
        # Re-assert topmost so it doesn't get lost
        self.root.attributes("-topmost", True)

    def _toggle_settings(self):
        if self._settings_visible:
            self.settings_panel.place_forget()
        else:
            self.settings_panel.place(x=0, y=36, relwidth=1, relheight=1)
        self._settings_visible = not self._settings_visible

    def _save_settings(self):
        resume = self.resume_edit.get("1.0", tk.END).strip()
        jd = self.jd_edit.get("1.0", tk.END).strip()
        device_str = self.device_var.get()
        # Parse index from string like "[0] Microphone (Realtek...)"
        device_idx = None
        if "[" in device_str and "]" in device_str:
            try:
                device_idx = int(device_str.split("[")[1].split("]")[0])
            except: pass

        self.context_callback(resume, jd, device_idx)
        self._toggle_settings()

    def set_device_list(self, devices):
        """Populate the device dropdown. devices = list of [index, name] strings."""
        menu = self.device_menu["menu"]
        menu.delete(0, "end")
        for d in devices:
            menu.add_command(label=d, command=lambda v=d: self.device_var.set(v))
        if devices:
            self.device_var.set(devices[0])

    def _on_close(self):
        self.root.quit()
        self.root.destroy()

    # ── Run ─────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    def _trigger(): print("AI triggered!")
    def _ctx(r, j): print(f"Context saved  resume={len(r)}  jd={len(j)}")

    ui = TkOverlayUI(_trigger, _ctx)
    ui.update_status("Listening…", "ready")
    ui.update_meter(0.4)
    ui.set_suggestion("Waiting for interview questions…")
    ui.run()
