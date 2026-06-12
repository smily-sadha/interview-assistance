"""
llm.py
======
Sends the screenshot + question to an LLM and returns the answer text.

Strategy:
    1. Try the MAIN model first   -> Google Gemini (free, reads images).
    2. If that fails (rate limit, no key, network error), automatically
       fall back to Groq (also free, also reads images).

Both providers receive the same screenshot and the same system prompt,
so the answer format stays consistent no matter which one replies.
"""

import base64

from ..config import settings


class LLMError(Exception):
    """Raised when every provider failed to answer."""


def _ask_gemini(image_png, user_text: str) -> str:
    """Ask Google Gemini. image_png may be None for a text-only question."""
    from google import genai
    from google.genai import types

    if not settings.gemini_api_key:
        raise LLMError("No Gemini API key configured.")

    contents = [settings.system_prompt, user_text]
    if image_png:
        contents.append(types.Part.from_bytes(data=image_png, mime_type="image/jpeg"))

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
    )
    text = (response.text or "").strip()
    if not text:
        raise LLMError("Gemini returned an empty response.")
    return text


def _ask_groq(image_png, user_text: str) -> str:
    """Ask Groq (fallback). image_png may be None for a text-only question."""
    from groq import Groq

    if not settings.groq_api_key:
        raise LLMError("No Groq API key configured.")

    content = [{"type": "text",
                "text": settings.system_prompt + "\n\n" + user_text}]
    if image_png:
        # Images are passed as a base64 "data URL" in the message content.
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_png).decode()
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": content}],
    )
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("Groq returned an empty response.")
    return text


def ask(image_png=None, user_text: str = "Solve the problem on my screen.") -> tuple[str, str]:
    """
    Send a question (optionally with a screenshot) to the LLM and return
    (short_answer, full_answer).

    image_png may be None for a voice/text-only question.
    Tries Gemini first, then Groq. Raises LLMError if both fail.
    """
    errors = []

    for name, func in (("Gemini", _ask_gemini), ("Groq", _ask_groq)):
        try:
            raw = func(image_png, user_text)
            return _split_answer(raw)
        except Exception as exc:  # noqa: BLE001 - we want to try the next one
            errors.append(f"{name}: {exc}")

    raise LLMError("All providers failed.\n" + "\n".join(errors))


def _split_answer(raw: str) -> tuple[str, str]:
    """
    Return (short_answer, full_answer).

    - full_answer  = the ENTIRE response, cleaned for display. This is what
      the panel shows by default, so any code is ALWAYS visible no matter
      which section the model put it in.
    - short_answer = just the ANSWER section (for the optional compact view).

    The model is told to reply as:
        ANSWER:
        ...
        DETAILS:
        ...
    but we handle the case where it ignores the format.
    """
    raw = raw.strip()
    lower = raw.lower()

    # Extract the ANSWER section for the compact view (best effort).
    short = raw
    if "answer:" in lower:
        start = lower.index("answer:") + len("answer:")
        rest = raw[start:]
        rest_lower = rest.lower()
        if "details:" in rest_lower:
            short = rest[:rest_lower.index("details:")].strip()
        else:
            short = rest.strip()

    # Full view = the whole response, with the bare labels turned into
    # nicer Markdown headings (purely cosmetic).
    full = raw
    for label, heading in (("ANSWER:", "**Answer**\n"),
                           ("DETAILS:", "\n**Details**\n")):
        # Replace only a label that sits at the start of a line.
        for variant in (label, label.lower(), label.title()):
            full = full.replace(variant, heading)

    return short or raw, full or raw
