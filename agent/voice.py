"""voice.py — THE ONLY FILE THAT TALKS TO ELEVENLABS.

Same rule as llm.py owning the model and data.py owning the DEMO switch: if you
find yourself putting an xi-api-key header anywhere else, that is the bug.

JARVIS only *listens* here. Speaking is done by the browser, out of the voices
already installed on the machine — free, unmetered, and the audio never leaves
the room. This file exists for the other direction, because a browser's own
speech recognition is Chrome-only and ships the recording to Google, and this
account's speech-to-text costs nothing:

    tier free, 10,000 TTS characters/month — and speech-to-text draws none of
    them. Measured: character_count unchanged across transcriptions.

So the paid budget is untouched by anything in this file. If that ever stops
being true, that is the thing to check first.

The browser sends a WAV. That is deliberate: MediaRecorder produces webm/opus,
and the docs only promise "all major formats" without naming it, so the browser
encodes PCM to WAV instead — a format proven to work here rather than one
assumed to.

Multipart is built by hand because this project has no dependencies and is not
about to grow one for a single upload.

Run it directly to check the account:  python -m agent.voice
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/voice.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

BASE = "https://api.elevenlabs.io/v1"
NO_KEY = "no ELEVENLABS_API_KEY in .env — the microphone is off"

# A question, not a podcast. 30 seconds of 16 kHz mono WAV is about 1 MB.
MAX_AUDIO_BYTES = 4 * 1024 * 1024
MIN_AUDIO_BYTES = 2048          # below this there is no speech, only a click
TIMEOUT_SECONDS = 120


class VoiceUnavailable(RuntimeError):
    """No key. A configuration fact, not a failure."""


class VoiceFailed(RuntimeError):
    """The call was made and did not come back usable."""


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def reason() -> str | None:
    return None if data_mod.elevenlabs_key() else NO_KEY


def available() -> bool:
    return reason() is None


def model_name() -> str:
    return data_mod.setting("ELEVENLABS_STT_MODEL", "scribe_v1")


# ---------------------------------------------------------------------------
# Listening
# ---------------------------------------------------------------------------

def _multipart(fields: dict[str, str], blob: bytes,
               filename: str, ctype: str) -> tuple[bytes, str]:
    """An RFC 2388 body. No dependency does this for us."""
    boundary = f"----jarvis{uuid.uuid4().hex}"
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f"--{boundary}\r\n".encode())
        out.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        out.write(f"{value}\r\n".encode("utf-8"))
    out.write(f"--{boundary}\r\n".encode())
    out.write(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    out.write(f"Content-Type: {ctype}\r\n\r\n".encode())
    out.write(blob)
    out.write(f"\r\n--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def transcribe(audio: bytes) -> dict[str, object]:
    """WAV bytes in, words out.

    Raises VoiceUnavailable when there is no key, VoiceFailed with a sentence
    fit for the alert strip when the call itself goes wrong.
    """
    problem = reason()
    if problem:
        raise VoiceUnavailable(problem)

    if len(audio) < MIN_AUDIO_BYTES:
        raise VoiceFailed("that was too short to be a question")
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceFailed(
            f"that recording is {len(audio) // 1024} kB — keep it under "
            f"{MAX_AUDIO_BYTES // 1024 // 1024} MB"
        )

    fields = {"model_id": model_name()}
    # Naming the language measurably helps a short clip; JARVIS_LANG is already
    # how the rest of the app knows what language we are working in.
    lang = data_mod.language().split("-")[0].strip().lower()
    if lang:
        fields["language_code"] = lang

    body, ctype = _multipart(fields, audio, "question.wav", "audio/wav")
    request = urllib.request.Request(
        f"{BASE}/speech-to-text", data=body, method="POST",
        headers={"xi-api-key": data_mod.elevenlabs_key(), "Content-Type": ctype},
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise VoiceFailed(_explain(exc)) from None
    except urllib.error.URLError as exc:
        raise VoiceFailed(f"could not reach ElevenLabs — {exc.reason}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceFailed(f"speech-to-text failed: {exc}") from None

    text = str(payload.get("text") or "").strip()
    if not text:
        raise VoiceFailed("nothing was said, or it was too quiet to hear")

    return {
        "text": text,
        "language": payload.get("language_code"),
        "confidence": payload.get("language_probability"),
        "seconds": payload.get("audio_duration_secs"),
        "model": model_name(),
    }


def _explain(exc: urllib.error.HTTPError) -> str:
    """One sentence for the alert strip, from whatever ElevenLabs said."""
    try:
        detail = json.loads(exc.read().decode("utf-8", "replace"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        detail = {}

    status = detail.get("detail")
    status = status if isinstance(status, dict) else {}
    code = str(status.get("status") or "").lower()
    message = str(status.get("message") or "").strip()

    if exc.code == 401:
        return "ElevenLabs rejected the key — check ELEVENLABS_API_KEY in .env"
    if exc.code == 429 or "quota" in code or "limit" in code:
        return "ElevenLabs is rate limiting or out of quota — try again shortly"
    if exc.code == 422:
        return f"ElevenLabs could not read that recording{': ' + message if message else ''}"
    if message:
        return f"ElevenLabs: {message}"[:300]
    return f"ElevenLabs returned {exc.code}"


# ---------------------------------------------------------------------------
# Account, for the terminal — never for the browser
# ---------------------------------------------------------------------------

def account() -> dict[str, object]:
    """Tier and TTS budget. Free to query, and we spend none of that budget."""
    if not available():
        return {}
    request = urllib.request.Request(
        f"{BASE}/user/subscription",
        headers={"xi-api-key": data_mod.elevenlabs_key()},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            sub = json.loads(response.read())
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "tier": sub.get("tier"),
        "tts_used": sub.get("character_count"),
        "tts_limit": sub.get("character_limit"),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    problem = reason()
    if problem:
        print(f"  listening  UNAVAILABLE — {problem}")
        return 1

    who = account()
    print(f"  listening  {model_name()} on the {who.get('tier')} tier")
    print(f"  language   {data_mod.language() or 'auto-detect'}")
    print(f"  speaking   the browser, using this machine's own voices (free)")
    print(f"  tts budget {who.get('tts_used')} / {who.get('tts_limit')} characters — "
          f"untouched, nothing here spends it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
