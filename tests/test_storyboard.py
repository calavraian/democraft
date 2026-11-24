"""Unit tests for DemoCraft minimal storyboard validator & caption extractor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import storyboard


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_minimal_promo_storyboard_validates_without_optional_fields(tmp_path: Path) -> None:
    # Arrange: only minimal fields — wide creative freedom, no freeze/cue required
    sb_file = _write_json(
        tmp_path / "storyboard.json",
        {
            "name": "goalpad-teaser",
            "mode": "promo",
            "default_lang": "es",
            "scenes": [
                {
                    "id": "hook",
                    "duration_s": 4.0,
                    "intent": "Gancho visual sobre el caos de hojas de cálculo.",
                    "captions": {"es": "¿Sigues manejando tu academia en hojas de cálculo?"},
                },
                {
                    "id": "reveal",
                    "duration_s": 14.0,
                    "intent": "Mostrar GoalPad con libertad visual orgánica.",
                    "captions": {"es": "Conoce GoalPad: tu asistente de academia y cancha."},
                    "creative_note": "extra freeform fields are always allowed",
                },
            ],
        },
    )

    # Act
    data = storyboard.load_storyboard(sb_file)
    report = storyboard.validate_storyboard(data)

    # Assert
    assert report["valid"] is True
    assert report["mode"] == "promo"
    assert report["total_duration_s"] == 18.0
    assert report["duration_status"] == "within_target"
    assert report["errors"] == []


def test_tutorial_grace_margin_allows_slight_overrun_with_warning() -> None:
    # Arrange: 155s exceeds 150s soft cap but stays inside +10s grace margin (160s)
    data = {
        "name": "goalpad-full-walkthrough",
        "mode": "tutorial",
        "scenes": [
            {"id": "step_1", "duration_s": 80.0, "freeze_s": 4.0, "freeze_mode": "before_action"},
            {"id": "step_2", "duration_s": 75.0, "freeze_s": 3.0, "freeze_mode": "after_action"},
        ],
    }

    # Act
    report = storyboard.validate_storyboard(data)

    # Assert
    assert report["valid"] is True
    assert report["total_duration_s"] == 155.0
    assert report["duration_status"] == "within_grace"
    assert any("grace" in w.lower() for w in report["warnings"])
    assert report["suggest_split"] is False


def test_tutorial_over_grace_recommends_splitting_into_parts() -> None:
    # Arrange: 175s exceeds 150s + 10s grace margin
    data = {
        "name": "too-long-tutorial",
        "mode": "tutorial",
        "scenes": [
            {"id": "part_a", "duration_s": 90.0},
            {"id": "part_b", "duration_s": 85.0},
        ],
    }

    # Act
    report = storyboard.validate_storyboard(data)

    # Assert
    assert report["valid"] is True  # advisory soft boundary — never hard-crashes creativity
    assert report["duration_status"] == "exceeds_grace"
    assert report["suggest_split"] is True
    assert any("split" in w.lower() for w in report["warnings"])


def test_invalid_freeze_settings_are_rejected() -> None:
    # Arrange
    data = {
        "name": "bad-freeze",
        "mode": "tutorial",
        "scenes": [
            {"id": "s1", "duration_s": 5.0, "freeze_s": 6.0, "freeze_mode": "before_action"},
            {"id": "s2", "duration_s": 5.0, "freeze_s": 1.0, "freeze_mode": "middle_of_nowhere"},
        ],
    }

    # Act
    report = storyboard.validate_storyboard(data)

    # Assert
    assert report["valid"] is False
    assert any("freeze_s" in e for e in report["errors"])
    assert any("freeze_mode" in e for e in report["errors"])


def test_extract_captions_builds_cumulative_timeline_and_exports_srt(tmp_path: Path) -> None:
    # Arrange
    data = {
        "name": "bilingual-guide",
        "mode": "tutorial",
        "default_lang": "es",
        "scenes": [
            {
                "id": "step_1",
                "duration_s": 5.0,
                "captions": {"es": "Abre Asistencia.", "en": "Open Attendance."},
            },
            {
                "id": "step_2",
                "duration_s": 6.0,
                "captions": {"es": "Marca los jugadores presentes.", "en": "Mark present players."},
            },
        ],
    }

    # Act
    cues_es = storyboard.extract_captions(data, lang="es")
    cues_en = storyboard.extract_captions(data, lang="en")
    out_srt = tmp_path / "guide-en.srt"
    storyboard.export_storyboard_srt(data, out_srt, lang="en")

    # Assert
    assert len(cues_es) == 2
    assert cues_es[0].start == pytest.approx(0.2, abs=0.01)
    assert cues_es[0].end == pytest.approx(4.8, abs=0.01)
    assert cues_es[1].start == pytest.approx(5.2, abs=0.01)
    assert cues_es[1].end == pytest.approx(10.8, abs=0.01)
    assert cues_en[1].text == "Mark present players."
    assert "Open Attendance." in out_srt.read_text(encoding="utf-8")
