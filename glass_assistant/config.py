"""
config.py
=========
ALL settings for the app live here in one place, so anyone can read this
single file and understand how the app behaves.

API keys are NOT written here. They are read from a `.env` file so your
secrets never end up in the source code.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Read the .env file (if present) into environment variables.
load_dotenv()


@dataclass
class Settings:
    # ---- API keys (loaded from .env) -------------------------------------
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    # ---- Models ----------------------------------------------------------
    # Main model: Google Gemini (can read images directly).
    gemini_model: str = "gemini-2.5-flash"
    # Fallback model: Groq (a vision-capable Llama model).
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # Speech-to-text engine:
    #   "groq"  = Groq-hosted Whisper. Stable, no native code, no live
    #             captions. DEFAULT because it always works.
    #   "local" = faster-whisper on your machine. Gives LIVE partial
    #             captions, but its engine (ctranslate2) needs the Microsoft
    #             Visual C++ Redistributable installed, or it crashes on load.
    #             Install it, then set this to "local":
    #             https://aka.ms/vs/17/release/vc_redist.x64.exe
    stt_engine: str = "groq"
    whisper_model: str = "whisper-large-v3"      # Groq-hosted fallback model
    stt_language: str = ""                        # "" = auto-detect, or "en"

    # ---- Screenshot (smaller image = faster LLM response) ---------------
    screenshot_monitor: int = 1      # 1 = primary monitor, 0 = all monitors
    screenshot_max_px: int = 1600    # longest side; downscaled before sending
    screenshot_jpeg_quality: int = 80

    # ---- Local faster-whisper -------------------------------------------
    # Model size: tiny / base / small / medium / large-v3 (bigger = better
    # but slower). "base" is a good free CPU default. First run downloads it.
    local_whisper_model: str = "base"
    local_whisper_device: str = "cpu"            # "cpu" or "cuda" (if you have a GPU)
    local_whisper_compute: str = "int8"          # "int8" (cpu) / "float16" (cuda)
    partial_interval_ms: int = 600                # how often live captions refresh

    # ---- Voice input -----------------------------------------------------
    voice_enabled: bool = True       # start listening as soon as the app runs
    # Where to listen:
    #   "loopback" = system audio  -> the OTHER person in Zoom/Meet (recommended)
    #   "mic"      = your microphone -> your own voice
    audio_source: str = "loopback"
    # Force a specific playback device for loopback (substring of its name,
    # e.g. "Headphones"). Empty = auto-pick the default speaker. Use
    # list_audio.py to see the available device names.
    audio_device_name: str = ""
    audio_sample_rate: int = 16000   # Whisper/VAD expect 16 kHz mono
    vad_aggressiveness: int = 2      # 0 (lenient) .. 3 (strict) speech filter
    vad_silence_ms: int = 800        # 0.8s of silence = "you finished talking"
    vad_start_ms: int = 150          # need this much speech before we start
    audio_max_seconds: int = 30      # hard cap on a single utterance
    voice_debug: bool = True         # print mic level + transcripts to the terminal

    # ---- Global hotkeys (work even when another app is focused) ----------
    # Format follows the `pynput` library, e.g. "<ctrl>+<space>".
    hotkey_capture: str = "<ctrl>+<space>"        # Capture screen + ask the AI
    hotkey_expand: str = "<ctrl>+<shift>+e"       # Toggle short / full answer
    hotkey_toggle: str = "<ctrl>+<shift>+h"       # Show / hide the glass panel
    hotkey_clickthrough: str = "<ctrl>+<shift>+t" # Toggle click-through mode
    hotkey_mute: str = "<ctrl>+<shift>+m"         # Mute / unmute the microphone
    hotkey_chat: str = "<ctrl>+<shift>+c"         # Open / close the chat box
    hotkey_quit: str = "<ctrl>+<shift>+q"         # Quit the app

    # ---- Glass window appearance ----------------------------------------
    window_width: int = 560          # starting width  (you can resize it)
    window_height: int = 480         # starting height (you can resize it)
    window_min_width: int = 340
    window_min_height: int = 180
    margin: int = 24                 # distance from the screen edge (pixels)
    # R, G, B, Alpha (0-255). Higher alpha = more solid / easier to read.
    background_color: tuple = (22, 24, 34, 238)
    text_color: str = "#FFFFFF"
    accent_color: str = "#7CC4FF"

    # ---- Behaviour -------------------------------------------------------
    hide_from_capture: bool = True   # Invisible in screen-share / recording
    # Click-through OFF by default so you can DRAG and RESIZE the window.
    # Toggle it on with the click-through hotkey when you want clicks to
    # pass through to the app behind.
    click_through: bool = False

    # The instruction we send to the model. The panel shows the full reply,
    # rendered as Markdown.
    system_prompt: str = field(default=(
        "You are an on-screen assistant. The user either captured their screen "
        "(you get a screenshot) or asked a question out loud (you get the "
        "transcribed text). They may have ONE problem or SEVERAL questions "
        "(code/errors, interview or test questions, math, or general "
        "questions).\n\n"
        "Answer EVERY distinct question or problem in the screenshot and/or the "
        "spoken question - do NOT answer only the first one.\n\n"
        "Format your reply in Markdown:\n"
        "- If there are multiple questions, put each under its own short "
        "heading (e.g. `## What is Docker`) and answer them in order.\n"
        "- If there is only one problem, just answer it directly.\n"
        "- When code is requested, write the FULL, runnable code inside a "
        "``` fenced code block - NEVER just describe it in words.\n"
        "- Keep each answer complete but concise (a few sentences or the code "
        "plus a short note). Don't pad.\n"
        "- If nothing looks like a question, say so and suggest what you can "
        "help with."
    ))

    def validate(self) -> list[str]:
        """Return a list of human-readable problems with the configuration."""
        problems = []
        if not self.gemini_api_key:
            problems.append("GEMINI_API_KEY is missing (add it to your .env file).")
        if not self.groq_api_key:
            problems.append("GROQ_API_KEY is missing (fallback will be disabled).")
        return problems


# A single shared settings object the rest of the app imports.
settings = Settings()
