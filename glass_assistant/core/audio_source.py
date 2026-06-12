"""
audio_source.py
===============
Pluggable audio input. Two sources, same tiny interface:

    with open_source() as src:
        frame = src.read_frame(frame_len)   # -> 16-bit mono PCM bytes

- LoopbackSource ("loopback"): captures SYSTEM audio with WASAPI loopback
  via the `soundcard` library. This is what plays through your speakers/
  headphones - i.e. the other person's voice in Zoom/Meet. It works even
  with headphones on, because it taps the digital stream, not the air.

- MicSource ("mic"): captures your microphone via `sounddevice`.

Both return exactly `frame_len` samples of 16 kHz mono signed-16-bit PCM,
which is what WebRTC-VAD and Whisper expect.
"""

from ..config import settings


class MicSource:
    """Microphone capture (your own voice)."""

    def __enter__(self):
        import sounddevice as sd
        self._stream = sd.RawInputStream(
            samplerate=settings.audio_sample_rate,
            blocksize=0,
            dtype="int16",
            channels=1,
        )
        self._stream.start()
        return self

    def read_frame(self, frame_len: int) -> bytes:
        data, _ = self._stream.read(frame_len)
        return bytes(data)

    def __exit__(self, *exc):
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass


class LoopbackSource:
    """System-audio capture (the other person in a call)."""

    def __enter__(self):
        # `soundcard` initialises COM itself, on whichever thread first
        # imports it. Because we import it HERE (on the audio thread), its
        # COM setup happens on the right thread. We must NOT call
        # CoInitializeEx ourselves first - doing so picks a COM mode that
        # conflicts with soundcard's and corrupts its COM library.
        import soundcard as sc
        self._cm = self._make_recorder(sc)
        self._rec = self._cm.__enter__()
        return self

    def _make_recorder(self, sc):
        loopbacks = [m for m in sc.all_microphones(include_loopback=True)
                     if getattr(m, "isloopback", False)]
        if not loopbacks:
            raise RuntimeError(
                "No system-audio loopback device found. Make sure a playback "
                "device is active."
            )

        chosen = None
        want = settings.audio_device_name.strip().lower()
        if want:
            # User forced a device by (partial) name.
            chosen = next((m for m in loopbacks if want in m.name.lower()), None)
        if chosen is None:
            # Match the loopback that belongs to the default speaker.
            try:
                spk = sc.default_speaker().name.lower()
                chosen = next((m for m in loopbacks
                               if spk in m.name.lower() or m.name.lower() in spk), None)
            except Exception:
                chosen = None
        if chosen is None:
            chosen = loopbacks[0]

        print(f"[voice] loopback device: {chosen.name}", flush=True)
        return chosen.recorder(samplerate=settings.audio_sample_rate, channels=1)

    def read_frame(self, frame_len: int) -> bytes:
        import numpy as np
        data = self._rec.record(numframes=frame_len)   # float32, shape (n, ch)
        mono = data.mean(axis=1) if getattr(data, "ndim", 1) > 1 else data
        mono = np.asarray(mono).flatten()
        # Guarantee exactly frame_len samples (VAD needs an exact frame size).
        if len(mono) < frame_len:
            mono = np.pad(mono, (0, frame_len - len(mono)))
        else:
            mono = mono[:frame_len]
        pcm = np.clip(mono, -1.0, 1.0) * 32767.0
        return pcm.astype("<i2").tobytes()

    def __exit__(self, *exc):
        try:
            self._cm.__exit__(*exc)
        except Exception:
            pass


def open_source(source_name: str = None):
    """Return an audio source as a context manager ('mic' or 'loopback')."""
    name = source_name or settings.audio_source
    if name == "mic":
        return MicSource()
    return LoopbackSource()
