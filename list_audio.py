"""
list_audio.py — show audio devices and which loopback actually has sound.

Usage:
    1. START PLAYING AUDIO (e.g. a YouTube video) so there's something to hear.
    2. python list_audio.py

It records ~1.5s from every system-audio (loopback) device and prints the
peak level. The device with a non-zero peak is the one to use. If a device
other than the default has the sound, copy its name into config.py:

    audio_device_name = "part of that device's name"
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import soundcard as sc

SR = 16000
SECONDS = 1.5

print("Default speaker     :", sc.default_speaker().name)
print("Default microphone  :", sc.default_microphone().name)

loopbacks = [m for m in sc.all_microphones(include_loopback=True)
             if getattr(m, "isloopback", False)]

print(f"\nFound {len(loopbacks)} loopback (system-audio) device(s).")
print(">>> Make sure audio is PLAYING now, then watch the peaks <<<\n")

for m in loopbacks:
    try:
        with m.recorder(samplerate=SR, channels=1) as rec:
            data = rec.record(numframes=int(SR * SECONDS))
        peak = float(np.abs(data).max())
        bar = "#" * int(min(peak, 1.0) * 40)
        flag = "  <-- HAS SOUND" if peak > 0.001 else "  (silent)"
        print(f"{m.name[:45]:45s} peak={peak:6.4f} {bar}{flag}")
    except Exception as exc:  # noqa: BLE001
        print(f"{m.name[:45]:45s} ERROR: {exc}")

print("\nIf the device with sound is NOT your default speaker, set its name in")
print("config.py ->  audio_device_name = \"...\"")
