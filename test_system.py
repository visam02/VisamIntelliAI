import unittest
import numpy as np
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from audio_engine import AudioEngine
from stt_module import STTModule
from llm_module import LLMModule


class TestAudioEngine(unittest.TestCase):
    def test_init(self):
        eng = AudioEngine(lambda s: None, lambda l: None)
        self.assertIsNotNone(eng)
        print("OK: AudioEngine initialized")

    def test_get_devices(self):
        devices = AudioEngine.get_devices()
        self.assertIsInstance(devices, list)
        print(f"OK: Found {len(devices)} input devices")

    def test_set_device(self):
        eng = AudioEngine(lambda s: None, lambda l: None)
        eng.set_device(0)
        self.assertEqual(eng._device_index, 0)
        print("OK: set_device works")


class TestSTTModule(unittest.TestCase):
    def test_init(self):
        stt = STTModule(model_size="tiny")
        self.assertIsNotNone(stt)
        print("OK: STTModule initialized")

    def test_hallucination_filter(self):
        """Known hallucinations should be filtered out."""
        self.assertIn("thank you", STTModule.HALLUCINATIONS)
        self.assertIn("subscribe", STTModule.HALLUCINATIONS)
        print("OK: hallucination filter populated")


class TestLLMModule(unittest.TestCase):
    def test_init_no_key(self):
        llm = LLMModule(api_key=None)
        self.assertFalse(llm.is_ready)
        print("OK: LLMModule without key → not ready")

    def test_init_with_dummy_key(self):
        llm = LLMModule(api_key="sk-test")
        self.assertTrue(llm.is_ready)
        print("OK: LLMModule with dummy key → ready")

    def test_set_context(self):
        llm = LLMModule(api_key="sk-test")
        llm.set_context("My resume text", "Job description text")
        self.assertIn("resume", llm._context.lower())
        print("OK: set_context stores data")

    def test_no_key_returns_warning(self):
        llm = LLMModule(api_key=None)
        result = llm.get_suggestion("test")
        self.assertIn("API Key", result)
        print("OK: no-key path returns warning string")


class TestQuestionDetection(unittest.TestCase):
    def setUp(self):
        from main import question_score
        self.score = question_score

    def test_question_mark(self):
        s = self.score("What is your name?")
        self.assertGreaterEqual(s, 3)
        print(f"OK: '?' detected, score={s}")

    def test_question_word(self):
        s = self.score("How do you handle conflict at work")
        self.assertGreaterEqual(s, 3)
        print(f"OK: question-word start, score={s}")

    def test_statement(self):
        s = self.score("I worked at Google")
        self.assertLess(s, 3)
        print(f"OK: statement scores low, score={s}")

    def test_tell_me(self):
        s = self.score("Tell me about yourself and your experience")
        self.assertGreaterEqual(s, 2)
        print(f"OK: 'tell me' phrase detected, score={s}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
