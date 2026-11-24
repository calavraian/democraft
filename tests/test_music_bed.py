"""Unit tests for DemoCraft multi-mood procedural music bed generator (`music_bed.py`)."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import music_bed


def test_generate_all_four_moods_and_beat_grid(tmp_path: Path) -> None:
    for mood in music_bed.MOOD_SPECS:
        out_wav = tmp_path / f"{mood}.wav"
        beats_json = tmp_path / f"{mood}.beats.json"
        meta = music_bed.generate_music_bed(
            mood=mood,
            duration_s=3.0,
            output_wav=out_wav,
            output_beats_json=beats_json,
        )

        assert out_wav.exists()
        assert beats_json.exists()
        assert meta["mood"] == mood
        assert meta["bpm"] == music_bed.MOOD_SPECS[mood]["bpm"]

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getframerate() == music_bed.SAMPLE_RATE
            assert pytest.approx(wf.getnframes() / wf.getframerate(), abs=0.05) == 3.0

        cues = json.loads(beats_json.read_text(encoding="utf-8"))
        assert cues["tempo"] == meta["bpm"]
        assert len(cues["beats"]) >= 4
        assert len(cues["strongCues"]) >= 1


def test_generate_music_bed_validates_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported mood"):
        music_bed.generate_music_bed("heavy-metal-chaos", 5.0, tmp_path / "x.wav")

    with pytest.raises(ValueError, match="Duration must be positive"):
        music_bed.generate_music_bed("modern-clean", 0.0, tmp_path / "x.wav")
