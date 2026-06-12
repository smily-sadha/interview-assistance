"""
stt.py
======
Speech-to-text using Groq-hosted Whisper Large V3.

Groq's Whisper is a fast FILE-transcription endpoint (OpenAI-compatible),
not a live stream. We record a short utterance (see voice.py), then send
the finished WAV here and get the text back in about a second.
"""

from ..config import settings


class STTError(Exception):
    """Raised when transcription fails."""


def transcribe(wav_bytes: bytes) -> str:
    """Send WAV audio to Groq Whisper and return the recognised text."""
    from groq import Groq

    if not settings.groq_api_key:
        raise STTError("No Groq API key configured (needed for Whisper).")

    client = Groq(api_key=settings.groq_api_key)
    result = client.audio.transcriptions.create(
        file=("speech.wav", wav_bytes),
        model=settings.whisper_model,
        response_format="text",
    )

    # With response_format="text" the SDK returns a plain string; with
    # other formats it returns an object with a `.text` attribute.
    text = result if isinstance(result, str) else getattr(result, "text", "")
    return (text or "").strip()


def transcribe_pcm(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """Wrap raw 16-bit mono PCM into a WAV and transcribe it with Groq."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return transcribe(buffer.getvalue())
