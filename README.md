# Glass Assistant 🪟🤖

A transparent, always-on-top AI helper for **Windows**. Press a hotkey, it
captures your screen, sends it to a free LLM, and shows the solution in a
**glass panel** that floats over your work without blocking your view.

- 🪟 **Glass overlay** – see-through window, your desktop stays visible behind it
- ⌨️ **Hotkey driven** – one keypress to capture & answer (saves your free quota)
- 👁️ **Reads your screen** – sends the screenshot straight to a vision model
- 🆓 **Free LLMs** – Google **Gemini** (main) with **Groq** as automatic fallback
- 🕵️ **Hidden from screen-share** – invisible in Zoom/Meet/Teams/OBS recordings
- 🧩 Helps with code/errors, interview & test questions, math, and general questions

---

## 1. Install

```powershell
# from the project folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Add your free API keys

1. Get a free **Gemini** key: https://aistudio.google.com/apikey
2. Get a free **Groq** key: https://console.groq.com/keys
3. Copy `.env.example` → `.env` and paste your keys in:

```powershell
copy .env.example .env
notepad .env
```

```env
GEMINI_API_KEY=AIza....your_real_key
GROQ_API_KEY=gsk_....your_real_key
```

## 3. Run

```powershell
python run.py
```

---

## Two ways to ask

- **Screen:** press `Ctrl + Space` — it screenshots your screen and answers.
- **Voice:** it listens to your call. By default it captures **system audio**
  (`audio_source="loopback"`) — i.e. the **other person's voice in Zoom/Meet**,
  tapped digitally so it's clean and works even with **headphones on**. You'll
  see **live partial captions** (local **faster-whisper**); when the speaker
  pauses ~0.8s the question goes to the LLM. Falls back to **Groq Whisper Large
  V3** if the local model can't load. Mute anytime with `Ctrl + Shift + M`.

  > Switch to your own microphone by setting `audio_source = "mic"` in
  > [`config.py`](glass_assistant/config.py).

  > First voice use downloads the local model once (~140 MB for `base`) and
  > then works offline. Change the size/device in
  > [`config.py`](glass_assistant/config.py) (`local_whisper_model`,
  > `local_whisper_device`).

## Hotkeys

| Hotkey            | Action                                  |
|-------------------|-----------------------------------------|
| `Ctrl + Space`    | Capture the screen and ask the AI       |
| *(just speak)*    | Ask by voice (always-on capture + VAD)  |
| `Ctrl + Shift + C`| Open / close the chat box               |
| `Ctrl + Shift + M`| Mute / unmute listening                 |
| `Ctrl + Shift + E`| Toggle full answer ↔ compact view       |
| `Ctrl + Shift + T`| Toggle click-through (drag vs pass-thru)|
| `Ctrl + Shift + H`| Show / hide the glass panel             |
| `Ctrl + Shift + Q`| Quit the app                            |

You can change all of these in [`glass_assistant/config.py`](glass_assistant/config.py).

---

## Project layout

```
screening/
├── run.py                      # launcher: python run.py
├── requirements.txt            # dependencies
├── .env.example                # template for your API keys
└── glass_assistant/
    ├── config.py               # ALL settings + key loading (start here)
    ├── main.py                 # wires everything together
    ├── core/
    │   ├── capture.py          # screenshot -> PNG bytes
    │   ├── audio_source.py     # system-audio loopback OR mic (pluggable)
    │   ├── voice.py            # always-on VAD (partial + final audio)
    │   ├── local_stt.py        # local faster-whisper (live captions)
    │   ├── stt.py              # Groq Whisper Large V3 (fallback)
    │   └── llm.py              # Gemini (main) + Groq (fallback) router
    ├── ui/
    │   └── overlay.py          # the transparent glass window
    └── winapi/
        └── stealth.py          # click-through + hide-from-capture (Win32)
```

---

## How it works (the flow)

```
[Ctrl+Space] → capture.py (screenshot)
             → llm.py     (try Gemini → if it fails, try Groq)
             → overlay.py (show short answer; Ctrl+Shift+E for full details)
```

## Honest limitations

- **Hide-from-capture** blocks *software* recording only. A separate phone/camera
  pointed at your monitor can still see the panel — no software can stop that.
- Free LLM tiers have **rate limits**. When Gemini hits its limit, the app
  automatically retries with Groq.
- The model can be **wrong**. Always sanity-check important answers.
- Built for **Windows 10 (2004+) / Windows 11**. The stealth feature uses a
  Windows-only API.
