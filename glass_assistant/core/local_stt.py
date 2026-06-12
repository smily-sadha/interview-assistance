"""
local_stt.py
============
Local speech-to-text with faster-whisper (runs on your own machine).

Why local: it lets us transcribe the audio collected SO FAR, repeatedly,
while you are still talking - giving live "partial captions". A hosted
endpoint like Groq can only transcribe a finished clip, so it can't do
live partials.

The model is downloaded once (from Hugging Face) on first use and cached
locally; after that it works offline. `base` is a good free CPU default.
"""

import threading

from ..config import settings

_model = None         # the loaded WhisperModel (lazy)
_available = None     # None = not tried yet, True/False after load attempt
_lock = threading.Lock()


def load():
    """Load the model once (thread-safe). Raises if faster-whisper isn't usable."""
    global _model, _available
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        model = WhisperModel(
            settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute,
        )
        _model = model
        _available = True
    return _model


def is_available() -> bool:
    return bool(_available)


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe raw 16-bit mono PCM audio (what voice.py collects).

    faster-whisper expects a float32 array sampled at 16 kHz, so we convert
    the int16 samples to floats in the range [-1, 1].
    """
    import numpy as np

    model = load()
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(
        audio,
        language=(settings.stt_language or None),
        beam_size=1,          # fast; good enough for short utterances
        vad_filter=False,     # we already do our own VAD in voice.py
    )
    return "".join(seg.text for seg in segments).strip()
