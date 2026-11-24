"""Unit tests for DemoCraft BYO beat & cue analyzer (`analyze_beats.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_beats


def test_pick_strong_cues_respects_spacing_and_cap() -> None:
    # Arrange: dense onset candidates with varying strengths
    candidates = [
        (0.5, 0.95),
        (0.6, 0.90),  # too close to 0.5 -> suppressed
        (2.0, 0.88),
        (4.0, 0.92),
        (6.0, 0.70),
    ]

    # Act
    picked = analyze_beats.pick_strong_cues(candidates, min_gap_s=0.8, max_cues=3)

    # Assert: ordered by time, min spacing respected
    assert len(picked) == 3
    times = [c["time"] for c in picked]
    assert times == sorted(times)
    assert 0.6 not in times


def test_build_beat_grid_from_bpm_produces_expected_intervals() -> None:
    grid = analyze_beats.build_regular_beat_grid(bpm=120.0, duration_s=4.0)
    assert grid["tempo"] == 120.0
    assert grid["beats"][0]["time"] == 0.0
    assert grid["beats"][1]["time"] == 0.5
    assert grid["strongCues"][0]["time"] == 0.0
    assert grid["strongCues"][1]["time"] == 2.0
