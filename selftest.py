"""
selftest.py — find out what's breaking, one subsystem at a time.

Run it inside your venv:

    python selftest.py

Each subsystem is tested separately and prints PASS / FAIL. If the program
stops with NO "PASS" and NO traceback, the test it stopped on crashed
NATIVELY (a C-level crash Python can't catch) — that is your culprit.

Tip: tests run from safest to riskiest. The audio and Whisper tests are the
usual suspects for a silent crash.
"""

import sys
import traceback

# Windows terminals default to cp1252; force UTF-8 so output never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def step(name, fn):
    print(f"\n=== TEST: {name} ===", flush=True)
    try:
        fn()
        print(f"  [PASS] {name}", flush=True)
        return True
    except Exception:
        print(f"  [FAIL] {name}", flush=True)
        traceback.print_exc()
        return False


# --------------------------------------------------------------------------
def t_imports():
    import PyQt6, mss, numpy, webrtcvad        # noqa: F401
    print("  core libs import OK")
    try:
        import soundcard                       # noqa: F401
        print("  soundcard import OK")
    except Exception as e:
        print(f"  soundcard MISSING: {e}")
    try:
        import faster_whisper                  # noqa: F401
        print("  faster_whisper import OK")
    except Exception as e:
        print(f"  faster_whisper MISSING: {e}")


def t_config():
    from glass_assistant.config import settings
    print("  python      :", sys.version.split()[0])
    print("  audio_source:", settings.audio_source)
    print("  gemini key  :", "set" if settings.gemini_api_key else "MISSING")
    print("  groq key    :", "set" if settings.groq_api_key else "MISSING")


def t_capture():
    from glass_assistant.core import capture
    png = capture.grab_screenshot()
    print(f"  screenshot captured: {len(png)} bytes")


def t_vad():
    import webrtcvad
    v = webrtcvad.Vad(2)
    silent = b"\x00\x00" * 480       # 30 ms of silence @ 16 kHz
    print("  VAD on silence ->", v.is_speech(silent, 16000))


def t_gui():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from glass_assistant.ui.overlay import Overlay
    app = QApplication.instance() or QApplication([])
    ov = Overlay()
    ov.show()
    print("  window shown — keeping it open 3s (it should NOT crash)…", flush=True)
    QTimer.singleShot(3000, app.quit)
    app.exec()
    print("  window survived 3 seconds")


def t_audio_source():
    from glass_assistant.config import settings
    from glass_assistant.core.audio_source import open_source
    frame_len = int(settings.audio_sample_rate * 30 / 1000)
    print(f"  opening '{settings.audio_source}' and reading 20 frames…", flush=True)
    print("  (for loopback: play a YouTube video so there's audio)", flush=True)
    with open_source() as src:
        for i in range(20):
            frame = src.read_frame(frame_len)
            if len(frame) != frame_len * 2:
                raise AssertionError(f"frame {i} wrong size: {len(frame)}")
    print("  read 20 audio frames OK")


def t_local_stt():
    import numpy as np
    from glass_assistant.core import local_stt
    print("  loading faster-whisper model (first run downloads it)…", flush=True)
    local_stt.load()
    pcm = np.zeros(16000, dtype=np.int16).tobytes()   # 1s silence
    text = local_stt.transcribe_pcm(pcm, 16000)
    print("  transcribe(silence) ->", repr(text))


if __name__ == "__main__":
    print("Glass Assistant self-test\n" + "=" * 40, flush=True)
    step("library imports", t_imports)
    step("config + API keys", t_config)
    step("screenshot capture", t_capture)
    step("WebRTC VAD", t_vad)
    step("GUI window (3s)", t_gui)
    step("audio source (mic/loopback)", t_audio_source)
    step("local STT (faster-whisper)", t_local_stt)
    print("\n" + "=" * 40, flush=True)
    print("Done. If it stopped early with no PASS/traceback, the test it", flush=True)
    print("stopped on is the one crashing natively — tell me which.", flush=True)
