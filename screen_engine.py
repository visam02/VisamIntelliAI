import pyautogui
import pytesseract
from PIL import Image
import numpy as np
import cv2

class ScreenEngine:
    def __init__(self, tesseract_path=None):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        self.last_text = ""

    def capture_and_ocr(self, region=None):
        """
        region: (x, y, width, height)
        """
        try:
            # Take screenshot
            screenshot = pyautogui.screenshot(region=region)
            screenshot_np = np.array(screenshot)
            
            # Preprocess for better OCR
            gray = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2GRAY)
            # Thresholding to get black text on white background (or vice versa)
            _, threshold = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            
            # OCR
            text = pytesseract.image_to_string(threshold)
            
            if text.strip() and text != self.last_text:
                self.last_text = text
                return text.strip()
        except Exception as e:
            print(f"Screen capture error: {e}")
        return None

if __name__ == "__main__":
    # Test capture
    engine = ScreenEngine()
    print("Capturing screen in 3 seconds...")
    import time
    time.sleep(3)
    text = engine.capture_and_ocr()
    print(f"Detected Text:\n{text}")
