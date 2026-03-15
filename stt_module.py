import threading
import queue
import numpy as np
import os
import io
import tempfile
import time

# ---------------------------------------------------------------------------
# STTModule – speech-to-text using Groq's cloud Whisper API for real-time
# speed, with local faster_whisper as a fallback.
# ---------------------------------------------------------------------------

class STTModule:
    """Real-time speech-to-text via Groq Whisper API (fast) or local model (fallback)."""

    HALLUCINATIONS = frozenset(["...", ".", ""])

    def __init__(self, result_callback=None, model_size=None):
        self.result_callback = result_callback
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._ready = threading.Event()

        # Decide: use Groq cloud API or local model
        self._use_cloud = False
        self._groq_client = None
        self._local_model = None
        self._model_size = model_size or os.environ.get("STT_MODEL", "base")

        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL", "")

        if api_key and "groq" in base_url.lower():
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=api_key)
                self._use_cloud = True
                print("[STT] using Groq cloud Whisper (fast, accurate)", flush=True)
            except ImportError:
                print("[STT] groq package not installed, trying openai client...", flush=True)
                try:
                    from openai import OpenAI
                    self._groq_client = OpenAI(
                        api_key=api_key,
                        base_url="https://api.groq.com/openai/v1"
                    )
                    self._use_cloud = True
                    print("[STT] using Groq cloud Whisper via openai client", flush=True)
                except Exception as e:
                    print(f"[STT] cloud init failed: {e}, falling back to local", flush=True)

        if not self._use_cloud:
            print(f"[STT] using local model '{self._model_size}' on CPU (may be slow)", flush=True)

    # -- lifecycle ------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name="STTWorker")
        self._thread.start()

    def wait_ready(self, timeout=60):
        return self._ready.wait(timeout=timeout)

    def stop(self):
        self._running = False
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    # -- public API -----------------------------------------------------------

    def enqueue(self, audio_segment):
        if self._running:
            # Drop old segments if queue is backing up (keep it real-time)
            if self._queue.qsize() > 3:
                try:
                    self._queue.get_nowait()  # drop oldest
                except queue.Empty:
                    pass
            self._queue.put(audio_segment)

    # -- internals ------------------------------------------------------------

    def _worker(self):
        if self._use_cloud:
            print("[STT] cloud mode ready (no model download needed)", flush=True)
        else:
            self._load_local_model()

        self._ready.set()
        print("[STT] worker ready", flush=True)

        while self._running:
            try:
                item = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if item is None:
                break

            t0 = time.time()

            if self._use_cloud:
                text = self._transcribe_cloud(item)
            else:
                text = self._transcribe_local(item)

            elapsed = time.time() - t0

            if text and text.lower().strip() not in self.HALLUCINATIONS and len(text.strip()) >= 2:
                print(f"[STT] ({elapsed:.1f}s) {text}", flush=True)
                if self.result_callback:
                    try:
                        self.result_callback(text)
                    except Exception as e:
                        print(f"[STT] callback error: {e}", flush=True)

    def _transcribe_cloud(self, audio_data):
        """Send audio to Groq's Whisper API and return text."""
        try:
            # Convert float32 numpy array to WAV bytes
            wav_bytes = self._numpy_to_wav(audio_data)

            # Create a temporary file (Groq API needs a file-like object)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    response = self._groq_client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file,
                        language="en",
                        response_format="text",
                    )

                # Response is either a string or has a .text attribute
                if isinstance(response, str):
                    return response.strip()
                return response.text.strip() if hasattr(response, 'text') else str(response).strip()
            finally:
                try:
                    os.unlink(tmp_path)
                except:
                    pass

        except Exception as e:
            print(f"[STT] cloud error: {e}", flush=True)
            return ""

    def _numpy_to_wav(self, audio_data, sample_rate=16000):
        """Convert float32 numpy array to WAV bytes."""
        import struct

        # Ensure float32
        audio_data = audio_data.astype(np.float32)

        # Convert to int16 PCM
        pcm = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        pcm_bytes = pcm.tobytes()

        # Build WAV header
        num_channels = 1
        sample_width = 2  # int16
        byte_rate = sample_rate * num_channels * sample_width
        block_align = num_channels * sample_width
        data_size = len(pcm_bytes)

        header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
        fmt = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels,
                          sample_rate, byte_rate, block_align, sample_width * 8)
        data_header = struct.pack('<4sI', b'data', data_size)

        return header + fmt + data_header + pcm_bytes

    def _load_local_model(self):
        from faster_whisper import WhisperModel
        print(f"[STT] loading local model '{self._model_size}' on CPU...", flush=True)
        try:
            self._local_model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            # Warm-up
            silence = np.zeros(16000, dtype=np.float32)
            self._local_model.transcribe(silence, beam_size=1, language="en")
            print("[STT] local model loaded + warm-up done", flush=True)
        except Exception as e:
            print(f"[STT] local model FAILED: {e}", flush=True)

    def _transcribe_local(self, audio_data):
        if self._local_model is None:
            return ""
        amp = float(np.abs(audio_data).max())
        if amp < 0.001:
            return ""
        try:
            segments, _ = self._local_model.transcribe(audio_data, beam_size=1, language="en")
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            print(f"[STT] local error: {e}", flush=True)
            return ""


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    results = []
    def _on_result(text):
        print(f"  >> {text}")
        results.append(text)

    stt = STTModule(result_callback=_on_result)
    stt.start()
    stt.wait_ready()

    # Feed silence
    stt.enqueue(np.zeros(32000, dtype=np.float32))
    time.sleep(2)
    stt.stop()
    print(f"Results: {results}")
