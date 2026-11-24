"""Unit tests for DemoCraft multi-language caption validator & SRT exporter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import captions


def test_load_and_validate_happy_path(tmp_path: Path) -> None:
    # Arrange
    data = {
        "default_lang": "es",
        "languages": {
            "es": [
                {"start": 0.4, "end": 3.4, "text": "Organiza tu academia desde un solo lugar."},
                {"start": 3.6, "end": 7.0, "text": "Asistencia, partidos y finanzas al instante."},
            ],
            "en": [
                {"start": 0.4, "end": 3.4, "text": "Run your sports academy in one place."},
            ],
        },
    }
    cap_file = tmp_path / "captions.json"
    cap_file.write_text(json.dumps(data), encoding="utf-8")

    # Act
    cues = captions.load_captions(cap_file, lang="es")
    report = captions.validate_cues(cues)

    # Assert
    assert len(cues) == 2
    assert report["valid"] is True
    assert report["errors"] == []
    assert report["warnings"] == []


def test_validate_catches_overlap_and_bad_bounds() -> None:
    # Arrange
    bad_cues = [
        captions.CaptionCue(start=0.5, end=3.0, text="First cue"),
        captions.CaptionCue(start=2.8, end=5.0, text="Overlapping cue"),
        captions.CaptionCue(start=6.0, end=5.5, text="Inverted cue"),
    ]

    # Act
    report = captions.validate_cues(bad_cues)

    # Assert
    assert report["valid"] is False
    assert any("overlap" in err.lower() for err in report["errors"])
    assert any("end must be greater than start" in err.lower() for err in report["errors"])


def test_validate_warns_when_cue_too_fast_to_read() -> None:
    # Arrange: 12 words in 1.0s violates ~0.3s/word reading floor
    fast_cues = [
        captions.CaptionCue(
            start=0.0,
            end=1.0,
            text="This caption has way too many words to read inside one second",
        )
    ]

    # Act
    report = captions.validate_cues(fast_cues)

    # Assert
    assert report["valid"] is True
    assert len(report["warnings"]) == 1
    assert "reading speed" in report["warnings"][0].lower()


def test_format_srt_timestamp_and_export(tmp_path: Path) -> None:
    # Arrange
    cues = [
        captions.CaptionCue(start=0.45, end=3.2, text="Hola GoalPad"),
        captions.CaptionCue(start=65.125, end=70.0, text="Segundo bloque"),
    ]
    out_srt = tmp_path / "es.srt"

    # Act
    captions.export_srt(cues, out_srt)
    content = out_srt.read_text(encoding="utf-8")

    # Assert
    assert "1\n00:00:00,450 --> 00:00:03,200\nHola GoalPad\n" in content
    assert "2\n00:01:05,125 --> 00:01:10,000\nSegundo bloque\n" in content


def test_load_captions_raises_on_unknown_language(tmp_path: Path) -> None:
    cap_file = tmp_path / "captions.json"
    cap_file.write_text(json.dumps({"languages": {"es": []}}), encoding="utf-8")

    with pytest.raises(KeyError, match="fr"):
        captions.load_captions(cap_file, lang="fr")


def test_load_captions_accepts_storyboard_json_directly(tmp_path: Path) -> None:
    # Arrange
    sb_file = tmp_path / "storyboard.json"
    sb_file.write_text(
        json.dumps(
            {
                "mode": "tutorial",
                "default_lang": "es",
                "scenes": [
                    {"id": "s1", "duration_s": 4.0, "captions": {"es": "Paso uno."}},
                    {"id": "s2", "duration_s": 5.0, "captions": {"es": "Paso dos."}},
                ],
            }
        ),
        encoding="utf-8",
    )

    # Act
    cues = captions.load_captions(sb_file, lang="es")

    # Assert
    assert len(cues) == 2
    assert cues[0].text == "Paso uno."
    assert cues[1].text == "Paso dos."
