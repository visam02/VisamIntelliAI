from stt_module import STTModule
import numpy as np
import time

print("--- STT Diagnostic ---")
try:
    print("Loading STT model...")
    stt = STTModule("tiny") # use tiny for faster test
    print("STT loaded successfully.")
    
    # Create 1 second of silence
    silent_audio = np.zeros(16000, dtype=np.float32)
    print("Testing transcription...")
    text = stt.transcribe(silent_audio)
    print(f"Transcription result: '{text}'")
    print("✓ STT Diagnostic Passed")
except Exception as e:
    import traceback
    print(f"✗ STT Diagnostic Failed: {e}")
    traceback.print_exc()
