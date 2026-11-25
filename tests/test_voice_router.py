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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert voice_router.select_provider("auto") == "kokoro"


def test_select_provider_cascade_supports_openai_and_elevenlabs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-key")
    assert voice_router.select_provider("auto") == "elevenlabs"

    monkeypatch.setenv("OPENAI_API_KEY", "oa-test-key")
    assert voice_router.select_provider("auto") == "openai"
    assert voice_router.select_provider("elevenlabs") == "elevenlabs"

    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-key")
    assert voice_router.select_provider("auto") == "gemini"
    assert voice_router.select_provider("openai") == "openai"
    assert voice_router.select_provider("auto", offline=True) == "kokoro"


def test_openai_tts_stdlib_request_writes_wav_and_measures_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    wav_sample = _write_dummy_wav(tmp_path / "sample.wav", seconds=2.5).read_bytes()
    captured: dict[str, object] = {}

    class FakeResp:
        def __enter__(self) -> "FakeResp":
            return self
        def __exit__(self, *args: object) -> None:
            pass
        def read(self) -> bytes:
            return wav_sample

    def fake_urlopen(req, timeout: float = 60.0):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-123")
    monkeypatch.setattr(voice_router.urllib.request, "urlopen", fake_urlopen)
    out = tmp_path / "openai_out.wav"

    # Act
    res = voice_router.route_voice(
        text="Hola mundo comercial.",
        output_path=out,
        provider_mode="openai",
        lang="es",
        mode="promo",
    )

    # Assert
    assert res["provider"] == "openai"
    assert res["model"] == "gpt-4o-mini-tts"
    assert out.exists()
    assert pytest.approx(res["audio_duration_seconds"], abs=0.05) == 2.5
    assert captured["url"] == "https://api.openai.com/v1/audio/speech"
    assert captured["auth"] == "Bearer sk-test-openai-123"
    assert captured["body"]["response_format"] == "wav"
    assert "instructions" in captured["body"]


def test_elevenlabs_tts_stdlib_wraps_pcm_into_valid_wav(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange: 1.5 seconds of 16-bit mono PCM @ 24000 Hz
    raw_pcm = b"\x00\x00" * int(1.5 * 24000)
    captured: dict[str, object] = {}

    class FakeResp:
        def __enter__(self) -> "FakeResp":
            return self
        def __exit__(self, *args: object) -> None:
            pass
        def read(self) -> bytes:
            return raw_pcm

    def fake_urlopen(req, timeout: float = 60.0):
        captured["url"] = req.full_url
        captured["api_key"] = req.get_header("Xi-api-key")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-secret-456")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "customVoice123")
    monkeypatch.setattr(voice_router.urllib.request, "urlopen", fake_urlopen)
    out = tmp_path / "eleven_out.wav"

    # Act
    res = voice_router.route_voice(
        text="Prueba de estudio.",
        output_path=out,
        provider_mode="elevenlabs",
        lang="es",
        mode="promo",
    )

    # Assert
    assert res["provider"] == "elevenlabs"
    assert res["voice"] == "customVoice123"
    assert out.exists()
    assert out.read_bytes()[:4] == b"RIFF"
    assert pytest.approx(res["audio_duration_seconds"], abs=0.05) == 1.5
    assert "customVoice123" in str(captured["url"])
    assert "output_format=pcm_24000" in str(captured["url"])
    assert captured["api_key"] == "el-secret-456"
    assert captured["body"]["model_id"] == "eleven_multilingual_v2"


def test_elevenlabs_free_tier_402_auto_falls_back_to_premade_voice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import io
    import urllib.error

    raw_pcm = b"\x00\x00" * int(1.0 * 24000)
    requested_urls: list[str] = []

    class FakeResp:
        def __enter__(self) -> "FakeResp":
            return self
        def __exit__(self, *args: object) -> None:
            pass
        def read(self) -> bytes:
            return raw_pcm

    def fake_urlopen(req, timeout: float = 60.0):
        requested_urls.append(req.full_url)
        if "paidLibraryVoice999" in req.full_url:
            err_body = json.dumps(
                {
                    "detail": {
                        "code": "paid_plan_required",
                        "message": "Free users cannot use library voices via the API.",
                    }
                }
            ).encode("utf-8")
            raise urllib.error.HTTPError(
                req.full_url, 402, "Payment Required", {}, io.BytesIO(err_body)
            )
        return FakeResp()

    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-free-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "paidLibraryVoice999")
    monkeypatch.setattr(voice_router.urllib.request, "urlopen", fake_urlopen)
    out = tmp_path / "fallback_out.wav"

    res = voice_router.route_voice(
        text="Hola prueba plan gratis.",
        output_path=out,
        provider_mode="elevenlabs",
        lang="es",
        mode="promo",
    )

    assert len(requested_urls) == 2
    assert res["provider"] == "elevenlabs"
    assert res["voice"] == voice_router.DEFAULT_VOICES[("elevenlabs", "es")]
    assert res["fallback_applied"] is True
    assert "warning" in res
    assert out.exists()


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
