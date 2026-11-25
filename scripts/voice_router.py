#!/usr/bin/env python3
"""DemoCraft pluggable VoiceRouter (Strategy cascade, zero global installs).

Provider cascade:
  1. `none`       -> Mute / captions-only (no voice track generated)
  2. `byo`        -> User-provided voiceover file (`--voice-file`)
  3. `gemini`     -> Google Gemini 3.8 Flash TTS via `v1beta` `interactions.create` +
                     structured `speech_metadata` (GEMINI_API_KEY)
  4. `openai`     -> OpenAI TTS (`gpt-4o-mini-tts`) via pure-stdlib REST HTTP (OPENAI_API_KEY)
  5. `elevenlabs` -> ElevenLabs TTS (`eleven_multilingual_v2`) via pure-stdlib REST HTTP (ELEVENLABS_API_KEY)
  6. `kokoro`     -> Offline $0 fallback via `kokoro-onnx` (ephemeral `uv` run)

Always returns exact `audio_duration_seconds` to support audio-first scene timing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any

from captions import load_captions

KOKORO_RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
DEFAULT_KOKORO_CACHE = Path.home() / ".cache" / "democraft" / "kokoro"
OPENAI_TTS_ENDPOINT = "https://api.openai.com/v1/audio/speech"
ELEVENLABS_TTS_BASE = "https://api.elevenlabs.io/v1/text-to-speech"

STYLE_PRESETS: dict[tuple[str, str], str] = {
    ("es", "promo"): (
        "neutral Latin American Spanish commercial voiceover, warm, upbeat, persuasive, "
        "crisp modern product-launch energy with natural emotive emphasis"
    ),
    ("en", "promo"): (
        "natural American English commercial voiceover, warm, upbeat, persuasive, "
        "crisp modern product-launch energy"
    ),
    ("es", "tutorial"): (
        "neutral Latin American Spanish friendly tutorial guide, calm, clear, warm, "
        "steady unhurried pacing for a step-by-step product walkthrough"
    ),
    ("en", "tutorial"): (
        "natural American English friendly tutorial guide, calm, clear, warm, "
        "steady unhurried pacing for a step-by-step product walkthrough"
    ),
}

DEFAULT_VOICES: dict[tuple[str, str], str] = {
    ("gemini", "es"): "Puck",
    ("gemini", "en"): "Kore",
    ("openai", "es"): "coral",
    ("openai", "en"): "alloy",
    ("elevenlabs", "es"): "JBFqnCBsd6RMkjVDRZzb",
    ("elevenlabs", "en"): "JBFqnCBsd6RMkjVDRZzb",
    ("kokoro", "es"): "ef_dora",
    ("kokoro", "en"): "af_heart",
}


def load_local_env(env_path: Path) -> None:
    """Loads KEY=VALUE pairs from a local env file without overriding existing vars or logging secrets."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def select_provider(provider_mode: str = "auto", offline: bool = False) -> str:
    """Resolves the active TTS provider following DemoCraft's validated cascade."""
    mode = provider_mode.strip().lower()
    if mode in ("none", "gemini", "openai", "elevenlabs", "kokoro"):
        return mode
    if mode != "auto":
        raise ValueError(
            f"Unsupported voice provider '{provider_mode}'. "
            "Choose auto|gemini|openai|elevenlabs|kokoro|none."
        )
    if offline:
        return "kokoro"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ELEVENLABS_API_KEY"):
        return "elevenlabs"
    return "kokoro"


def measure_wav_duration(wav_path: Path) -> float:
    """Measures WAV audio duration in seconds using Python stdlib `wave`."""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return round(frames / float(rate), 2) if rate > 0 else 0.0


def extract_narration_text(source_path: Path, lang: str | None = None) -> str:
    """Extracts concatenated spoken text from a storyboard.json, captions.json, or .txt file."""
    if not source_path.is_file():
        raise FileNotFoundError(f"Script/storyboard file not found: {source_path}")
    if source_path.suffix.lower() == ".txt":
        return source_path.read_text(encoding="utf-8").strip()
    cues = load_captions(source_path, lang=lang)
    return " ".join(c.text.strip() for c in cues if c.text.strip())


def _run_gemini_ephemeral(
    text: str,
    output_path: Path,
    voice: str,
    style: str,
    model: str = "auto",
) -> dict[str, Any]:
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY is required when provider='gemini'.")
    if not shutil.which("uv"):
        raise RuntimeError("`uv` is required for zero-bloat Gemini TTS execution.")

    worker = r'''
import base64, json, os, re, sys, time, wave
from pathlib import Path
from google import genai
from google.genai import types

payload = json.loads(sys.stdin.read())
client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(api_version="v1beta"),
)

model = payload["model"]
if model == "auto":
    ver_re = re.compile(r"gemini-(\d+(?:\.\d+)?)")
    def rank(name):
        lo = name.lower()
        m = ver_re.search(lo)
        v = float(m.group(1)) if m else 0.0
        return (1 if "tts" in lo else 0, v, 1 if "pro" in lo else 0, 0 if "lite" in lo else 1, 0 if ("preview" in lo or "exp" in lo) else 1, lo)
    tts_models = sorted({m.name.removeprefix("models/") for m in client.models.list() if "tts" in m.name.lower()}, key=rank, reverse=True)
    if not tts_models:
        raise RuntimeError("No Gemini TTS models available on v1beta for this API key.")
    model = tts_models[0]

content_item = {"type": "text", "text": payload["text"]}
if payload.get("style"):
    content_item["annotations"] = [{"type": "speech_metadata", "style": payload["style"]}]

t0 = time.perf_counter()
interaction = client.interactions.create(
    model=model,
    input=[{"type": "user_input", "content": [content_item]}],
    response_format={"type": "audio"},
    generation_config={"speech_config": [{"voice": payload["voice"]}]},
)
elapsed = time.perf_counter() - t0

raw_data = interaction.output_audio.data
audio_bytes = base64.b64decode(raw_data) if isinstance(raw_data, str) else bytes(raw_data)
out_path = Path(payload["output_path"])
out_path.parent.mkdir(parents=True, exist_ok=True)
if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
    out_path.write_bytes(audio_bytes)
else:
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(audio_bytes)

with wave.open(str(out_path), "rb") as wf:
    dur = wf.getnframes() / float(wf.getframerate())

print(json.dumps({
    "provider": "gemini",
    "model": model,
    "voice": payload["voice"],
    "output_path": str(out_path),
    "generation_seconds": round(elapsed, 2),
    "audio_duration_seconds": round(dur, 2),
    "size_kb": round(out_path.stat().st_size / 1024.0, 1),
}))
'''
    req_json = json.dumps(
        {
            "text": text,
            "output_path": str(output_path.resolve()),
            "voice": voice,
            "style": style,
            "model": model,
        },
        ensure_ascii=False,
    )
    proc = subprocess.run(
        ["uv", "run", "--quiet", "--with", "google-genai>=3.0.0", "python", "-c", worker],
        input=req_json,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Gemini TTS failed:\n{proc.stderr[-1200:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _ensure_kokoro_models(cache_dir: Path) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "kokoro-v1.0.fp16.onnx"
    voices_path = cache_dir / "voices-v1.0.bin"
    for target, fname in (
        (model_path, "kokoro-v1.0.fp16.onnx"),
        (voices_path, "voices-v1.0.bin"),
    ):
        if not target.is_file():
            url = f"{KOKORO_RELEASE_BASE}/{fname}"
            urllib.request.urlretrieve(url, target)
    return model_path, voices_path


def _run_kokoro_ephemeral(
    text: str,
    output_path: Path,
    voice: str,
    lang: str,
    speed: float = 1.0,
    cache_dir: Path = DEFAULT_KOKORO_CACHE,
) -> dict[str, Any]:
    if not shutil.which("uv"):
        raise RuntimeError("`uv` is required for zero-bloat Kokoro ONNX execution.")

    model_path, voices_path = _ensure_kokoro_models(cache_dir)
    kokoro_lang = "es-419" if lang.lower().startswith("es") else "en-us"

    worker = r'''
import json, sys, time
from pathlib import Path
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro

payload = json.loads(sys.stdin.read())
ort.set_default_logger_severity(3)
t0 = time.perf_counter()
k = Kokoro(payload["model_path"], payload["voices_path"])
samples, sr = k.create(
    payload["text"],
    voice=payload["voice"],
    speed=payload["speed"],
    lang=payload["lang"],
)
elapsed = time.perf_counter() - t0
out_path = Path(payload["output_path"])
out_path.parent.mkdir(parents=True, exist_ok=True)
sf.write(str(out_path), samples, sr)
dur = len(samples) / float(sr)
print(json.dumps({
    "provider": "kokoro",
    "model": Path(payload["model_path"]).name,
    "voice": payload["voice"],
    "lang": payload["lang"],
    "output_path": str(out_path),
    "generation_seconds": round(elapsed, 2),
    "audio_duration_seconds": round(dur, 2),
    "size_kb": round(out_path.stat().st_size / 1024.0, 1),
}))
'''
    req_json = json.dumps(
        {
            "text": text,
            "output_path": str(output_path.resolve()),
            "model_path": str(model_path),
            "voices_path": str(voices_path),
            "voice": voice,
            "lang": kokoro_lang,
            "speed": speed,
        },
        ensure_ascii=False,
    )
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--quiet",
            "--python",
            "3.12",
            "--with",
            "kokoro-onnx",
            "--with",
            "soundfile",
            "python",
            "-c",
            worker,
        ],
        input=req_json,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Kokoro local TTS failed:\n{proc.stderr[-1200:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _write_pcm_as_wav(pcm_bytes: bytes, output_path: Path, sample_rate: int = 24000) -> None:
    """Writes raw signed 16-bit mono PCM bytes into a standard RIFF/WAVE file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if pcm_bytes[:4] == b"RIFF" and pcm_bytes[8:12] == b"WAVE":
        output_path.write_bytes(pcm_bytes)
        return
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def _run_openai_tts(
    text: str,
    output_path: Path,
    voice: str,
    instructions: str,
    model: str = "gpt-4o-mini-tts",
) -> dict[str, Any]:
    """Synthesizes speech via OpenAI Audio Speech REST API using pure Python stdlib."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required when provider='openai'. "
            "Store it in a local gitignored .env file and pass --env-file (never paste keys in chat)."
        )

    payload: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "wav",
    }
    if instructions and "gpt-4o-mini-tts" in model:
        payload["instructions"] = instructions

    req = urllib.request.Request(
        OPENAI_TTS_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            audio_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"OpenAI TTS HTTP {exc.code}: {detail}") from None
    elapsed = time.perf_counter() - t0

    _write_pcm_as_wav(audio_bytes, output_path, sample_rate=24000)
    return {
        "provider": "openai",
        "model": model,
        "voice": voice,
        "output_path": str(output_path),
        "generation_seconds": round(elapsed, 2),
        "audio_duration_seconds": measure_wav_duration(output_path),
        "size_kb": round(output_path.stat().st_size / 1024.0, 1),
    }


def _run_elevenlabs_tts(
    text: str,
    output_path: Path,
    voice_id: str,
    model: str = "eleven_multilingual_v2",
    _allow_free_fallback: bool = True,
) -> dict[str, Any]:
    """Synthesizes speech via ElevenLabs REST API (pcm_24000 -> WAV) using pure Python stdlib.

    If a custom/library voice returns HTTP 402 `paid_plan_required` on a free-tier account,
    automatically falls back once to the included multilingual premade voice with a clear warning.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError(
            "ELEVENLABS_API_KEY is required when provider='elevenlabs'. "
            "Store it in a local gitignored .env file and pass --env-file (never paste keys in chat)."
        )

    safe_voice = urllib.parse.quote(voice_id.strip(), safe="")
    url = f"{ELEVENLABS_TTS_BASE}/{safe_voice}?output_format=pcm_24000"
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.78,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            pcm_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        premade_default = DEFAULT_VOICES[("elevenlabs", "en")]
        is_free_library_block = (
            exc.code == 402
            and ("paid_plan_required" in detail or "library voices" in detail.lower())
        )
        if _allow_free_fallback and is_free_library_block and voice_id.strip() != premade_default:
            fallback_res = _run_elevenlabs_tts(
                text=text,
                output_path=output_path,
                voice_id=premade_default,
                model=model,
                _allow_free_fallback=False,
            )
            fallback_res["fallback_applied"] = True
            fallback_res["requested_voice"] = voice_id
            fallback_res["warning"] = (
                f"Voice '{voice_id}' requires a paid ElevenLabs plan; automatically fell back "
                f"to free-tier premade multilingual voice '{premade_default}'."
            )
            return fallback_res
        raise RuntimeError(f"ElevenLabs TTS HTTP {exc.code}: {detail}") from None
    elapsed = time.perf_counter() - t0

    _write_pcm_as_wav(pcm_bytes, output_path, sample_rate=24000)
    return {
        "provider": "elevenlabs",
        "model": model,
        "voice": voice_id,
        "output_path": str(output_path),
        "generation_seconds": round(elapsed, 2),
        "audio_duration_seconds": measure_wav_duration(output_path),
        "size_kb": round(output_path.stat().st_size / 1024.0, 1),
    }


def route_voice(
    text: str,
    output_path: Path,
    provider_mode: str = "auto",
    lang: str = "es",
    mode: str = "promo",
    voice: str | None = None,
    style: str | None = None,
    gemini_model: str = "auto",
    openai_model: str = "gpt-4o-mini-tts",
    elevenlabs_model: str = "eleven_multilingual_v2",
    speed: float = 1.0,
    offline: bool = False,
    voice_file: Path | None = None,
    cache_dir: Path = DEFAULT_KOKORO_CACHE,
) -> dict[str, Any]:
    """Routes narration through BYO, Gemini, OpenAI, ElevenLabs, Kokoro offline, or none."""
    if voice_file is not None:
        if not voice_file.is_file():
            raise FileNotFoundError(f"BYO voice file not found: {voice_file}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if voice_file.resolve() != output_path.resolve():
            shutil.copy2(voice_file, output_path)
        dur = measure_wav_duration(output_path) if output_path.suffix.lower() == ".wav" else None
        return {
            "provider": "byo",
            "output_path": str(output_path),
            "audio_duration_seconds": dur,
            "size_kb": round(output_path.stat().st_size / 1024.0, 1),
        }

    chosen = select_provider(provider_mode=provider_mode, offline=offline)
    if chosen == "none":
        return {"provider": "none", "output_path": None, "audio_duration_seconds": 0.0}

    if not text or not text.strip():
        raise ValueError("Narration text cannot be empty when voice synthesis is enabled.")

    lang_key = "es" if lang.lower().startswith("es") else "en"
    mode_key = "tutorial" if mode.lower() == "tutorial" else "promo"
    chosen_style = style or STYLE_PRESETS[(lang_key, mode_key)]

    if chosen == "elevenlabs":
        chosen_voice = voice or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICES[(chosen, lang_key)]
        return _run_elevenlabs_tts(
            text=text.strip(),
            output_path=output_path,
            voice_id=chosen_voice,
            model=elevenlabs_model,
        )

    chosen_voice = voice or DEFAULT_VOICES[(chosen, lang_key)]

    if chosen == "gemini":
        return _run_gemini_ephemeral(
            text=text.strip(),
            output_path=output_path,
            voice=chosen_voice,
            style=chosen_style,
            model=gemini_model,
        )

    if chosen == "openai":
        return _run_openai_tts(
            text=text.strip(),
            output_path=output_path,
            voice=chosen_voice,
            instructions=chosen_style,
            model=openai_model,
        )

    return _run_kokoro_ephemeral(
        text=text.strip(),
        output_path=output_path,
        voice=chosen_voice,
        lang=lang_key,
        speed=speed,
        cache_dir=cache_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DemoCraft VoiceRouter (Gemini -> OpenAI -> ElevenLabs -> Kokoro -> BYO)."
    )
    parser.add_argument("--text", default=None, help="Direct narration text.")
    parser.add_argument("--from-file", type=Path, default=None, help="Extract text from storyboard.json, captions.json, or .txt.")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Target WAV path.")
    parser.add_argument(
        "--provider",
        choices=("auto", "gemini", "openai", "elevenlabs", "kokoro", "none"),
        default="auto",
    )
    parser.add_argument("--lang", default="es", help="Language code (es|en).")
    parser.add_argument("--mode", choices=("promo", "tutorial"), default="promo")
    parser.add_argument("--voice", default=None, help="Override voice name or ElevenLabs voice ID.")
    parser.add_argument("--style", default=None, help="Optional speech style/instructions override (Gemini/OpenAI).")
    parser.add_argument("--gemini-model", default="auto", help="Gemini TTS model ID or 'auto'.")
    parser.add_argument("--openai-model", default="gpt-4o-mini-tts", help="OpenAI TTS model ID.")
    parser.add_argument("--elevenlabs-model", default="eleven_multilingual_v2", help="ElevenLabs TTS model ID.")
    parser.add_argument("--speed", type=float, default=1.0, help="Kokoro speed (0.5..2.0).")
    parser.add_argument("--offline", action="store_true", help="Force offline Kokoro fallback.")
    parser.add_argument("--voice-file", type=Path, default=None, help="BYO voiceover file.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional local .env file for GEMINI_API_KEY / OPENAI_API_KEY / ELEVENLABS_API_KEY.",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_KOKORO_CACHE)
    args = parser.parse_args()

    if args.env_file:
        load_local_env(args.env_file)

    narration = args.text or ""
    if args.from_file:
        narration = extract_narration_text(args.from_file, lang=args.lang)

    summary = route_voice(
        text=narration,
        output_path=args.output,
        provider_mode=args.provider,
        lang=args.lang,
        mode=args.mode,
        voice=args.voice,
        style=args.style,
        gemini_model=args.gemini_model,
        openai_model=args.openai_model,
        elevenlabs_model=args.elevenlabs_model,
        speed=args.speed,
        offline=args.offline,
        voice_file=args.voice_file,
        cache_dir=args.cache_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
