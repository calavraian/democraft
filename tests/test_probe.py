"""Unit tests for DemoCraft capability probe (`probe.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import probe


def test_probe_detects_all_capabilities_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    fake_chrome = tmp_path / "Google Chrome"
    fake_chrome.write_text("", encoding="utf-8")
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("", encoding="utf-8")

    which_map = {
        "ffmpeg": "/usr/local/bin/ffmpeg",
        "uv": "/opt/homebrew/bin/uv",
        "docker": "/usr/local/bin/docker",
    }
    monkeypatch.setattr(probe.shutil, "which", lambda cmd: which_map.get(cmd))
    monkeypatch.setattr(probe, "find_chromium_browser", lambda: str(fake_chrome))
    monkeypatch.setattr(probe, "find_blender", lambda: str(fake_blender))
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value-never-returned")

    # Act
    report = probe.probe_environment()

    # Assert
    assert report["core_ready"] is True
    assert report["browser_path"] == str(fake_chrome)
    assert report["ffmpeg_strategy"] == "system"
    assert report["optional"]["blender_available"] is True
    assert report["optional"]["gemini_api_key_set"] is True
    assert "super-secret-value-never-returned" not in str(report)


def test_probe_falls_back_to_uv_when_system_ffmpeg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(probe.shutil, "which", lambda cmd: "/opt/homebrew/bin/uv" if cmd == "uv" else None)
    monkeypatch.setattr(probe, "find_chromium_browser", lambda: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    monkeypatch.setattr(probe, "find_blender", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # Act
    report = probe.probe_environment()

    # Assert
    assert report["core_ready"] is True
    assert report["ffmpeg_strategy"] == "uv"
    assert report["optional"]["blender_available"] is False
    assert report["optional"]["gemini_api_key_set"] is False


def test_probe_reports_not_ready_when_browser_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(probe.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(probe, "find_chromium_browser", lambda: None)
    monkeypatch.setattr(probe, "find_blender", lambda: None)

    # Act
    report = probe.probe_environment()

    # Assert
    assert report["core_ready"] is False
    assert report["ffmpeg_strategy"] == "none"
    assert len(report["missing_requirements"]) == 2


def test_probe_detects_multi_provider_tts_keys_and_env_file_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    monkeypatch.setattr(probe.shutil, "which", lambda cmd: "/opt/homebrew/bin/uv" if cmd == "uv" else None)
    monkeypatch.setattr(probe, "find_chromium_browser", lambda: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    monkeypatch.setattr(probe, "find_blender", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# User local keys\nOPENAI_API_KEY=sk-proj-secret-openai\nELEVENLABS_API_KEY=sk_secret_eleven\n",
        encoding="utf-8",
    )

    # Act
    report = probe.probe_environment(env_file=env_file)

    # Assert
    opt = report["optional"]
    assert opt["gemini_api_key_set"] is False
    assert opt["openai_api_key_set"] is True
    assert opt["elevenlabs_api_key_set"] is True
    assert opt["available_voice_providers"] == ["openai", "elevenlabs", "kokoro"]
    # Secrets must NEVER appear anywhere in the report
    serialized = str(report)
    assert "sk-proj-secret-openai" not in serialized
    assert "sk_secret_eleven" not in serialized
