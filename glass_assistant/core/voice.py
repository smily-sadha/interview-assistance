"""
voice.py
========
Always-on microphone listener with Voice Activity Detection (VAD).

It runs on a background thread and continuously reads the mic in tiny
30 ms frames. WebRTC-VAD labels each frame as speech or silence:

    - When enough speech frames arrive, we start collecting an utterance.
    - WHILE you keep talking, every ~0.6s it hands the audio-so-far to
      `on_partial(pcm)` so the UI can show a live caption.
    - When ~0.8s of silence follows, it hands the full clip to
      `on_final(pcm)` (which transcribes it and asks the LLM).

The callbacks receive RAW 16-bit mono PCM bytes (not WAV). Both the local
faster-whisper path and the Groq fallback know how to read that.

Muting just pauses collection without stopping the stream.
"""

import audioop
import threading

import webrtcvad

from ..config import settings
from .audio_source import open_source


class VoiceListener:
    def __init__(self, on_final, on_partial=None, on_error=None):
        # on_final(pcm)   -> called once when speech stops
        # on_partial(pcm) -> called repeatedly during speech (live caption)
        # on_error(msg)   -> called if the audio device can't be opened
        self.on_final = on_final
        self.on_partial = on_partial
        self.on_error = on_error
        self.enabled = settings.voice_enabled
        self._running = False
        self._thread = None

        self.sample_rate = settings.audio_sample_rate
        self.frame_ms = 30
        self.frame_len = int(self.sample_rate * self.frame_ms / 1000)   # samples
        self.frame_bytes = self.frame_len * 2                           # int16
        self.vad = webrtcvad.Vad(settings.vad_aggressiveness)

    # ------------------------------------------------------------- lifecycle
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_enabled(self, value: bool):
        self.enabled = value

    # --------------------------------------------------------------- the loop
    def _run(self):
        silence_needed = max(1, settings.vad_silence_ms // self.frame_ms)
        start_needed = max(1, settings.vad_start_ms // self.frame_ms)
        partial_every = max(1, settings.partial_interval_ms // self.frame_ms)
        max_frames = int(settings.audio_max_seconds * 1000 / self.frame_ms)

        frames = []          # collected audio for the current utterance
        triggered = False    # are we currently inside someone's speech?
        voiced_run = 0       # consecutive speech frames before triggering
        silence_run = 0      # consecutive silence frames after triggering
        since_partial = 0    # frames since the last live-caption update

        try:
            source_cm = open_source()
        except Exception as exc:  # noqa: BLE001
            # If system-audio (loopback) can't open, fall back to the mic so
            # voice still works instead of dying silently.
            if settings.audio_source == "loopback":
                if self.on_error:
                    self.on_error("system-audio failed; switched to microphone")
                try:
                    source_cm = open_source("mic")
                except Exception as exc2:  # noqa: BLE001
                    if self.on_error:
                        self.on_error(str(exc2))
                    return
            else:
                if self.on_error:
                    self.on_error(str(exc))
                return

        dbg_count = 0
        dbg_peak = 0

        try:
            with source_cm as source:
                print("[voice] audio stream open — listening", flush=True)
                while self._running:
                    frame = source.read_frame(self.frame_len)

                    # Debug level meter: every ~1s print how loud the captured
                    # audio is. ~0 means we're capturing silence (wrong device).
                    if settings.voice_debug and len(frame) == self.frame_bytes:
                        dbg_peak = max(dbg_peak, audioop.rms(frame, 2))
                        dbg_count += 1
                        if dbg_count >= 33:
                            print(f"[voice] level(rms)={dbg_peak} "
                                  f"triggered={triggered}", flush=True)
                            dbg_count, dbg_peak = 0, 0

                    # If muted, drop everything and reset state (but keep
                    # reading so the audio device doesn't overflow).
                    if not self.enabled or len(frame) != self.frame_bytes:
                        frames, triggered, voiced_run, silence_run = [], False, 0, 0
                        since_partial = 0
                        continue

                    is_speech = self.vad.is_speech(frame, self.sample_rate)

                    if not triggered:
                        if is_speech:
                            voiced_run += 1
                            frames.append(frame)
                            if voiced_run >= start_needed:
                                triggered = True
                                silence_run = 0
                                since_partial = 0
                        else:
                            voiced_run = 0
                            frames = []
                    else:
                        frames.append(frame)
                        since_partial += 1

                        if is_speech:
                            silence_run = 0
                        else:
                            silence_run += 1

                        # Live caption: emit audio-so-far every ~0.6s.
                        if self.on_partial and since_partial >= partial_every:
                            since_partial = 0
                            self._emit(self.on_partial, frames)

                        finished = silence_run >= silence_needed
                        too_long = len(frames) >= max_frames
                        if finished or too_long:
                            self._finalize(frames)
                            frames, triggered, voiced_run, silence_run = [], False, 0, 0
                            since_partial = 0
        except Exception as exc:  # noqa: BLE001
            if self.on_error:
                self.on_error(str(exc))

    # ----------------------------------------------------------- finalise
    def _finalize(self, frames):
        # Ignore very short blips (noise, a cough, etc.).
        if len(frames) < (settings.vad_start_ms // self.frame_ms) + 3:
            return
        if settings.voice_debug:
            print(f"[voice] utterance captured: {len(frames)} frames "
                  f"(~{len(frames) * self.frame_ms} ms) → transcribing", flush=True)
        self._emit(self.on_final, frames)

    def _emit(self, callback, frames):
        pcm = b"".join(frames)
        try:
            callback(pcm)
        except Exception:
            pass  # never let a callback error kill the listening loop
