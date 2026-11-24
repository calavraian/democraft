"""Unit tests for DemoCraft pluggable VoiceRouter (`voice_router.py`)."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import voice_router


def _write_dummy_wav(path: Path, seconds: float = 2.0, sr: int = 24000) -> Path:
    nframes = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * nframes)
    return path


def test_select_provider_cascade_prefers_gemini_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    assert voice_router.select_provider("auto") == "gemini"
    assert voice_router.select_provider("auto", offline=True) == "kokoro"
    assert voice_router.select_provider("none") == "none"


def test_select_provider_falls_back_to_kokoro_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert voice_router.select_provider("auto") == "kokoro"


def test_byo_voice_provider_copies_and_measures_duration(tmp_path: Path) -> None:
    src = _write_dummy_wav(tmp_path / "my_voice.wav", seconds=3.5)
    out = tmp_path / "out_voice.wav"

    res = voice_router.route_voice(
        text="Ignored for BYO",
        output_path=out,
        provider_mode="auto",
        voice_file=src,
    )

    assert res["provider"] == "byo"
    assert out.exists()
    assert pytest.approx(res["audio_duration_seconds"], abs=0.05) == 3.5


def test_none_voice_mode_returns_clean_skip(tmp_path: Path) -> None:
    res = voice_router.route_voice(
        text="Solo subtítulos",
        output_path=tmp_path / "unused.wav",
        provider_mode="none",
    )
    assert res["provider"] == "none"
    assert res["output_path"] is None


def test_extract_narration_from_storyboard(tmp_path: Path) -> None:
    sb = tmp_path / "storyboard.json"
    sb.write_text(
        json.dumps(
            {
                "default_lang": "es",
                "scenes": [
                    {"id": "s1", "duration_s": 4.0, "captions": {"es": "Primera frase."}},
                    {"id": "s2", "duration_s": 4.0, "captions": {"es": "Segunda frase."}},
                ],
            }
        ),
        encoding="utf-8",
    )
    text = voice_router.extract_narration_text(sb, lang="es")
    assert text == "Primera frase. Segunda frase."


def test_load_local_env_does_not_override_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEMOCRAFT_TEST_KEY", raising=False)
    env_file = tmp_path / ".env.local"
    env_file.write_text('DEMOCRAFT_TEST_KEY="from-file"\n', encoding="utf-8")
    voice_router.load_local_env(env_file)
    assert voice_router.os.environ["DEMOCRAFT_TEST_KEY"] == "from-file"
    monkeypatch.delenv("DEMOCRAFT_TEST_KEY", raising=False)
