import sys
import os

print("--- System Diagnostics ---")
print(f"Python version: {sys.version}")
print(f"Current Directory: {os.getcwd()}")

modules = [
    'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui',
    'sounddevice', 'numpy', 'openai', 'faster_whisper', 
    'keyboard', 'pyautogui', 'pytesseract', 'PIL', 'cv2'
]

for mod in modules:
    try:
        __import__(mod)
        print(f"OK: {mod} is installed")
    except ImportError as e:
        print(f"FAIL: {mod} is NOT installed: {e}")
    except Exception as e:
        print(f"ERROR: {mod} failed to load: {e}")

print("--- End Diagnostics ---")
