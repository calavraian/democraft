"""Unit tests for DemoCraft procedural SFX synthesizer (`sfx_synth.py`)."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sfx_synth


def test_synthesize_all_supported_sfx_presets(tmp_path: Path) -> None:
    for preset in sfx_synth.SFX_PRESETS:
        out = tmp_path / f"{preset}.wav"
        meta = sfx_synth.generate_sfx(preset, out, duration_s=0.35)
        assert out.exists()
        assert meta["preset"] == preset
        with wave.open(str(out), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == sfx_synth.SAMPLE_RATE
            assert wf.getnframes() > 0


def test_generate_sfx_rejects_unknown_preset_and_bad_duration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported SFX preset"):
        sfx_synth.generate_sfx("airhorn_mlg", tmp_path / "bad.wav")

    with pytest.raises(ValueError, match="Duration must be between"):
        sfx_synth.generate_sfx("whoosh", tmp_path / "bad.wav", duration_s=0.01)
