"""
test_logic.py — unit tests for the pure (no GUI / no network) logic.

Run either way:

    python -m pytest tests          # if you have pytest
    python tests/test_logic.py      # plain python, no pytest needed

These cover the answer parser and config validation — the bits most likely
to break silently when we change prompts or settings.
"""

import os
import sys

# Windows terminals default to cp1252; force UTF-8 so output never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Make the project importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glass_assistant.core.llm import _split_answer  # noqa: E402
from glass_assistant.config import Settings          # noqa: E402


def test_split_answer_with_labels():
    raw = "ANSWER:\nUse a set.\nDETAILS:\nSets give O(1) lookup."
    short, full = _split_answer(raw)
    assert "Use a set." in short
    assert "DETAILS" not in short          # short is only the ANSWER section
    assert "Sets give O(1)" in full        # full keeps everything


def test_split_answer_without_labels():
    raw = "Just a plain answer with no labels."
    short, full = _split_answer(raw)
    assert raw in short
    assert raw in full


def test_split_answer_keeps_code_in_full():
    raw = "ANSWER:\n```python\nprint('hi')\n```\nDETAILS:\nPrints hi."
    _short, full = _split_answer(raw)
    assert "print('hi')" in full           # code is never lost from the full view


def test_config_validate_reports_missing_keys():
    s = Settings(gemini_api_key="", groq_api_key="")
    problems = s.validate()
    assert any("GEMINI" in p for p in problems)
    assert any("GROQ" in p for p in problems)


def test_config_validate_ok_when_keys_present():
    s = Settings(gemini_api_key="x", groq_api_key="y")
    assert s.validate() == []


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    print("Running logic tests\n" + "=" * 30)
    sys.exit(0 if _run_all() else 1)
