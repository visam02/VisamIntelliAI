import sounddevice as sd
import numpy as np
import threading
import queue
import time
from collections import deque

# ---------------------------------------------------------------------------
# AudioEngine – captures mic audio and emits chunks on a FIXED INTERVAL
# for real-time transcription. No more waiting for silence gaps.
# ---------------------------------------------------------------------------

class AudioEngine:
    """Captures audio and emits segments every CHUNK_SEC for real-time STT."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCK_DURATION_MS = 100          # InputStream block size
    CHUNK_SEC = 2.0                  # Emit a chunk every 2 seconds of speech
    SILENCE_THRESHOLD = 0.002        # RMS below this = silence
    SILENCE_TIMEOUT_SEC = 1.5        # After this much silence, flush remaining buffer

    def __init__(self, segment_callback, meter_callback,
                 sample_rate=None, source="mic"):
        self.segment_callback = segment_callback
        self.meter_callback = meter_callback
        self.sample_rate = sample_rate or self.SAMPLE_RATE
        self.source = source

        self._block_size = int(self.sample_rate * self.BLOCK_DURATION_MS / 1000)
        self._chunk_blocks = int(self.CHUNK_SEC * 1000 / self.BLOCK_DURATION_MS)
        self._silence_blocks = int(self.SILENCE_TIMEOUT_SEC * 1000 / self.BLOCK_DURATION_MS)

        self._audio_queue = queue.Queue()
        self._recording = False
        self._thread = None
        self._device_index = None

    # -- public helpers -------------------------------------------------------

    @staticmethod
    def get_devices():
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "default_sr": d["default_samplerate"],
                    "is_default": i == sd.default.device[0],
                })
        return result

    def set_device(self, index):
        self._device_index = index

    # -- lifecycle ------------------------------------------------------------

    def start(self):
        if self._recording:
            return
        self._recording = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="AudioEngine")
        self._thread.start()

    def stop(self):
        self._recording = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def restart(self, device_index=None, source=None):
        self.stop()
        if device_index is not None:
            self._device_index = device_index
        if source is not None:
            self.source = source
        self.start()

    # -- internals ------------------------------------------------------------

    def _stream_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[AudioEngine] status: {status}", flush=True)
        self._audio_queue.put(indata[:, 0].copy())

    def _run(self):
        extra = {}
        if self.source == "loopback":
            extra = self._loopback_kwargs()
            if extra is None:
                print("[AudioEngine] loopback unavailable, using mic", flush=True)
                extra = {}

        print(f"[AudioEngine] start  device={self._device_index}  sr={self.sample_rate}", flush=True)

        try:
            with sd.InputStream(
                device=self._device_index,
                samplerate=self.sample_rate,
                channels=self.CHANNELS,
                blocksize=self._block_size,
                callback=self._stream_callback,
                **extra,
            ):
                print("[AudioEngine] stream opened", flush=True)
                self._chunking_loop()
        except Exception as e:
            print(f"[AudioEngine] CRITICAL: {e}", flush=True)
            self._recording = False

    def _loopback_kwargs(self):
        try:
            hostapis = sd.query_hostapis()
            wasapi_idx = None
            for idx, api in enumerate(hostapis):
                if "wasapi" in api["name"].lower():
                    wasapi_idx = idx
                    break
            if wasapi_idx is None:
                return None
            default_out = hostapis[wasapi_idx].get("default_output_device")
            if default_out is None:
                return None
            self._device_index = default_out
            return {"extra_settings": sd.WasapiSettings(exclusive=False)}
        except Exception as e:
            print(f"[AudioEngine] loopback error: {e}", flush=True)
            return None

    def _chunking_loop(self):
        """
        Fixed-interval chunking:
        - Buffer audio blocks continuously
        - Every CHUNK_SEC of speech, emit the buffer (don't wait for silence)
        - If silence lasts > SILENCE_TIMEOUT_SEC, flush whatever we have
        - This ensures text appears every ~2 seconds during continuous speech
        """
        buf = []
        speech_blocks = 0       # count of speech blocks in current buffer
        silence_count = 0       # consecutive silence blocks

        while self._recording:
            try:
                block = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # Meter update
            rms = float(np.sqrt(np.mean(block ** 2)))
            level = min(1.0, rms * 12)
            try:
                self.meter_callback(level)
            except:
                pass

            is_speech = rms > self.SILENCE_THRESHOLD
            buf.append(block)

            if is_speech:
                speech_blocks += 1
                silence_count = 0
            else:
                silence_count += 1

            # EMIT conditions:
            # 1) We've accumulated CHUNK_SEC worth of speech blocks -> emit now
            if speech_blocks >= self._chunk_blocks:
                self._emit(buf)
                buf = []
                speech_blocks = 0
                silence_count = 0

            # 2) We had speech, then silence timeout -> flush remaining
            elif speech_blocks > 2 and silence_count >= self._silence_blocks:
                self._emit(buf)
                buf = []
                speech_blocks = 0
                silence_count = 0

            # 3) Pure silence for too long with no speech -> just discard
            elif speech_blocks == 0 and silence_count >= self._silence_blocks:
                buf = []
                silence_count = 0

    def _emit(self, blocks):
        if len(blocks) < 3:
            return
        segment = np.concatenate(blocks).astype(np.float32)
        try:
            self.segment_callback(segment)
        except Exception as e:
            print(f"[AudioEngine] callback error: {e}", flush=True)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Devices:", AudioEngine.get_devices())

    def _on_seg(seg):
        print(f"  >> segment: {len(seg)/16000:.1f}s")

    def _on_meter(l):
        bars = int(l * 30)
        print(f"  {'|' * bars}{' ' * (30-bars)} {l:.2f}", end="\r")

    eng = AudioEngine(_on_seg, _on_meter)
    eng.start()
    print("Recording 10s... speak to test")
    time.sleep(10)
    eng.stop()
    print("\nDone.")
