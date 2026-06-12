"""
main.py
=======
The entry point that wires everything together.

Two ways to ask:

    Ctrl+Space  ->  capture screen        -> ask LLM -> show answer
    speak aloud ->  faster-whisper (local, live captions; Groq fallback)
                    -> ask LLM -> show answer
                    (always-on mic + VAD; mute with Ctrl+Shift+M)

Threading model:
- `pynput` listens for global hotkeys on a background thread.
- The voice listener runs the mic on its own thread (VAD).
- A single transcriber thread turns audio into text (so transcriptions
  never pile up or block the mic).
- LLM calls run on short-lived worker threads.
- All of them talk to the UI only through Qt signals (thread-safe).
"""

import sys
import threading
import traceback

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from pynput import keyboard

from .config import settings
from .core import capture, llm
from .ui.overlay import Overlay
from .winapi import stealth


class _Transcriber(threading.Thread):
    """
    Background worker that converts audio -> text.

    It keeps only the NEWEST pending job (a later partial replaces an older
    partial), but never lets a partial overwrite a pending final. Uses the
    local model when available, and Groq Whisper as a fallback for finals.
    """

    def __init__(self, sample_rate: int, on_text):
        super().__init__(daemon=True)
        self.sample_rate = sample_rate
        self.on_text = on_text                  # on_text(text, is_final)
        self._lock = threading.Lock()
        self._pending = None                    # (pcm_bytes, is_final)
        self._event = threading.Event()
        self._running = True

    def submit(self, pcm_bytes, is_final):
        with self._lock:
            if self._pending is not None and self._pending[1] and not is_final:
                return  # don't drop a queued final for a newer partial
            self._pending = (pcm_bytes, is_final)
        self._event.set()

    def run(self):
        from .core import local_stt, stt
        while self._running:
            self._event.wait()
            self._event.clear()
            with self._lock:
                job, self._pending = self._pending, None
            if not job:
                continue
            pcm, is_final = job

            text = None
            if settings.stt_engine == "local" and local_stt.is_available():
                try:
                    text = local_stt.transcribe_pcm(pcm, self.sample_rate)
                except Exception:
                    text = None
            if text is None and is_final:
                # Local model not ready/failed -> Groq fallback (finals only).
                try:
                    print("[stt] transcribing final utterance via Groq…", flush=True)
                    text = stt.transcribe_pcm(pcm, self.sample_rate)
                    print(f"[stt] result: {text!r}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"[stt] ERROR: {exc!r}", flush=True)
                    self.on_text(f"[STT error] {exc}", True)
                    continue
            if text is None:
                continue  # a partial while the local model isn't ready yet
            self.on_text(text, is_final)


class Controller(QObject):
    """Holds the Qt signals that connect background threads to the UI."""

    capture_requested = pyqtSignal()
    expand_requested = pyqtSignal()
    toggle_requested = pyqtSignal()
    clickthrough_requested = pyqtSignal()
    mute_requested = pyqtSignal()
    chat_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    caption_ready = pyqtSignal(str, bool)      # transcribed text, is_final
    answer_ready = pyqtSignal(str, str, str)   # short, full, source
    error_ready = pyqtSignal(str)
    status_ready = pyqtSignal(str)
    idle_ready = pyqtSignal()

    def __init__(self, overlay: Overlay):
        super().__init__()
        self.overlay = overlay
        self._busy = False
        self._click_through = settings.click_through
        self._mic_on = settings.voice_enabled
        self.voice = None
        self.transcriber = None

        # Conversation state (for Chat mode + memory).
        self._history = []            # [{"role": "user"/"assistant", "text": ...}]
        self._pending_question = None # question awaiting an answer (to log)
        self._last_heard = None       # last voice question (for the Answer button)

        self.capture_requested.connect(self._on_capture)
        self.expand_requested.connect(self.overlay.toggle_expand)
        self.toggle_requested.connect(self.overlay.toggle_visible)
        self.clickthrough_requested.connect(self._on_toggle_clickthrough)
        self.mute_requested.connect(self._on_mute)
        self.chat_requested.connect(lambda: self.overlay.toggle_chat())
        self.quit_requested.connect(QApplication.instance().quit)
        self.caption_ready.connect(self._on_caption)
        self.answer_ready.connect(self._on_answer)
        self.error_ready.connect(self._on_error)
        self.status_ready.connect(self.overlay.set_status)
        self.idle_ready.connect(self._on_idle)

        # Toolbar buttons on the overlay.
        self.overlay.analyse_requested.connect(self._on_capture)
        self.overlay.answer_requested.connect(self._on_answer_button)
        self.overlay.record_toggled.connect(self._on_mute)
        self.overlay.chat_submitted.connect(self._on_chat)
        self.overlay.new_chat_requested.connect(self._on_new_chat)

    # ----------------------------------------------------------- voice setup
    def start_voice(self):
        """Start the always-on mic + transcriber (degrades gracefully)."""
        if not settings.voice_enabled:
            return
        try:
            from .core.voice import VoiceListener
        except Exception as exc:  # noqa: BLE001
            self.overlay.set_status(f"🔇 Mic libs missing: {exc}")
            return

        print("[voice] starting transcriber thread", flush=True)
        self.transcriber = _Transcriber(
            settings.audio_sample_rate,
            on_text=lambda text, final: self.caption_ready.emit(text, final),
        )
        self.transcriber.start()

        print(f"[voice] opening audio source: {settings.audio_source}", flush=True)
        try:
            self.voice = VoiceListener(
                on_final=lambda pcm: self.transcriber.submit(pcm, True),
                on_partial=lambda pcm: self.transcriber.submit(pcm, False),
                on_error=lambda msg: self.status_ready.emit(f"🔇 Audio error: {msg}"),
            )
            self.voice.start()
        except Exception as exc:  # noqa: BLE001
            self.overlay.set_status(f"🔇 Audio unavailable: {exc}")
            return

        # Load the local model in the background so startup isn't blocked.
        self.overlay.set_status("🎤 Loading speech model…")
        threading.Thread(target=self._preload_model, daemon=True).start()

    def _preload_model(self):
        from .core import local_stt
        src = "system audio" if settings.audio_source == "loopback" else "mic"

        # Groq-only mode: never touch the local model (avoids any native
        # faster-whisper/ctranslate2 crash). Finals are transcribed by Groq.
        if settings.stt_engine != "local":
            print("[voice] STT engine = groq (hosted Whisper); skipping local model", flush=True)
            self.status_ready.emit(f"🎤 Listening ({src}, Groq Whisper)")
            return

        print("[voice] loading local STT model (faster-whisper)…", flush=True)
        try:
            local_stt.load()
            print("[voice] local STT model ready", flush=True)
            self.status_ready.emit(f"🎤 Listening ({src})")
        except Exception as exc:  # noqa: BLE001
            # Local model unavailable; we'll use the Groq Whisper fallback.
            print(f"[voice] local STT unavailable: {exc!r}", flush=True)
            if settings.groq_api_key:
                self.status_ready.emit(f"🎤 Listening ({src}, Groq Whisper, no live captions)")
            else:
                self.status_ready.emit("🔇 Voice off (install faster-whisper or add Groq key)")

    # ----------------------------------------------------------- toggles
    def _on_toggle_clickthrough(self):
        self._click_through = not self._click_through
        stealth.set_click_through(int(self.overlay.winId()), self._click_through)
        self.overlay.set_status(
            "Click-through ON (clicks pass through)" if self._click_through
            else "Click-through OFF (drag/resize enabled)"
        )

    def _on_mute(self):
        if not self.voice:
            return
        self._mic_on = not self._mic_on
        self.voice.set_enabled(self._mic_on)
        self.overlay.set_listening(self._mic_on)

    # ----------------------------------------------------------- screen path
    def _on_capture(self):
        if self._busy:
            return
        self._busy = True
        self._pending_question = "Analyse my screen"
        self.overlay.show_thinking()
        try:
            image_png = capture.grab_screenshot()
        except Exception as exc:  # noqa: BLE001
            self._busy = False
            self.overlay.show_error(f"Could not capture screen:\n{exc}")
            return
        threading.Thread(
            target=self._ask_llm, args=(image_png, None, "screen"), daemon=True
        ).start()

    # ----------------------------------------------------------- voice path
    def _on_caption(self, text: str, is_final: bool):
        if self._busy:
            return
        text = text.strip()
        if not is_final:
            if text:
                self.overlay.show_caption(text)     # live partial caption
            return
        if not text:
            self.overlay.set_listening(self._mic_on)
            return
        self._last_heard = text
        self._ask_question(text, "voice")

    # ----------------------------------------------------------- chat / answer
    def _on_chat(self, text: str):
        self._ask_question(text, "chat")

    def _on_new_chat(self):
        """Clear conversation memory and the panel."""
        self._history = []
        self._pending_question = None
        self._last_heard = None
        self.overlay.clear()

    def _on_answer_button(self):
        """Answer the last question heard from the call."""
        if self._last_heard:
            self._ask_question(self._last_heard, "voice")
        else:
            self.overlay.set_status("Nothing heard yet")

    def _ask_question(self, text: str, source: str):
        """Text-question path (voice / chat / answer button) with memory."""
        if self._busy:
            return
        self._busy = True
        self._pending_question = text
        self.overlay.show_heard(text)
        prompt = self._build_chat_prompt(text)
        threading.Thread(
            target=self._ask_llm, args=(None, prompt, source), daemon=True
        ).start()

    def _build_chat_prompt(self, new_text: str) -> str:
        """Fold recent conversation into the prompt so answers have context."""
        if not self._history:
            return new_text
        lines = ["Here is our conversation so far:"]
        for turn in self._history[-8:]:
            who = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{who}: {turn['text']}")
        lines.append(f"User: {new_text}")
        lines.append("Answer the latest User message, using the conversation "
                     "above for context.")
        return "\n".join(lines)

    # ----------------------------------------------------------- shared
    def _ask_llm(self, image_png, user_text, source):
        try:
            short, full = llm.ask(image_png, user_text) if user_text else llm.ask(image_png)
            self.answer_ready.emit(short, full, source)
        except Exception as exc:  # noqa: BLE001
            self.error_ready.emit(str(exc))

    def _on_answer(self, short: str, full: str, source: str):
        self._busy = False
        self.overlay.show_answer(short, full, source)
        # Remember this turn so Chat follow-ups have context.
        if self._pending_question is not None:
            self._history.append({"role": "user", "text": self._pending_question})
            self._history.append({"role": "assistant", "text": short})
            self._history = self._history[-16:]
            self._pending_question = None

    def _on_error(self, message: str):
        self._busy = False
        self._pending_question = None
        self.overlay.show_error(message)

    def _on_idle(self):
        self._busy = False
        self.overlay.set_listening(self._mic_on)


def _start_hotkeys(controller: Controller):
    hotkeys = {
        settings.hotkey_capture: controller.capture_requested.emit,
        settings.hotkey_expand: controller.expand_requested.emit,
        settings.hotkey_toggle: controller.toggle_requested.emit,
        settings.hotkey_clickthrough: controller.clickthrough_requested.emit,
        settings.hotkey_mute: controller.mute_requested.emit,
        settings.hotkey_chat: controller.chat_requested.emit,
        settings.hotkey_quit: controller.quit_requested.emit,
    }
    listener = keyboard.GlobalHotKeys(hotkeys)
    listener.daemon = True
    listener.start()
    return listener


def _apply_window_tricks(overlay: Overlay):
    hwnd = int(overlay.winId())
    if settings.hide_from_capture:
        stealth.hide_from_capture(hwnd, True)
    if settings.click_through:
        stealth.set_click_through(hwnd, True)


def _install_safe_excepthook():
    """Print slot errors instead of letting PyQt abort the whole process."""
    def hook(exctype, value, tb):
        traceback.print_exception(exctype, value, tb)
    sys.excepthook = hook


def _log(msg: str):
    print(f"[init] {msg}", flush=True)


def main():
    _install_safe_excepthook()
    _log("creating QApplication")
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    _log("building overlay window")
    overlay = Overlay()
    overlay.show()
    _log("applying window tricks (stealth/click-through)")
    _apply_window_tricks(overlay)

    problems = settings.validate()
    if problems:
        overlay.show_error("Setup notes:\n- " + "\n- ".join(problems))

    _log("wiring controller")
    controller = Controller(overlay)
    _log("starting global hotkeys")
    _start_hotkeys(controller)
    _log("starting voice listener")
    controller.start_voice()

    _log("entering Qt event loop (window should stay open now)")
    code = app.exec()
    _log(f"event loop exited with code {code}")


if __name__ == "__main__":
    main()
