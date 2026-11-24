#!/usr/bin/env python3
"""DemoCraft beat & strong-cue analyzer for BYO music tracks (stdlib + ephemeral uv).

Provides:
  - Pure-stdlib `build_regular_beat_grid()` and `pick_strong_cues()` helpers.
  - Zero-bloat `analyze_byo_track()` invoking `librosa` ephemerally via `uv` to
    extract BPM, `beats[]`, and `strongCues[]` from any user-supplied MP3/WAV.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def pick_strong_cues(
    candidates: list[tuple[float, float]],
    min_gap_s: float = 0.8,
    max_cues: int = 32,
) -> list[dict[str, Any]]:
    """Selects highest-energy cues with minimum spacing, returned sorted by time."""
    ranked = sorted(candidates, key=lambda pair: pair[1], reverse=True)
    chosen: list[tuple[float, float]] = []
    for t_s, strength in ranked:
        if len(chosen) >= max_cues:
            break
        if all(abs(t_s - existing_t) >= min_gap_s for existing_t, _ in chosen):
            chosen.append((t_s, strength))
    chosen.sort(key=lambda pair: pair[0])
    return [
        {"time": round(t_s, 3), "intensity": round(float(strength), 3), "kind": "strong_beat"}
        for t_s, strength in chosen
    ]


def build_regular_beat_grid(bpm: float, duration_s: float) -> dict[str, Any]:
    """Constructs an exact mathematical beat & bar-downbeat grid for known BPM."""
    if bpm <= 0 or duration_s <= 0:
        raise ValueError("BPM and duration_s must be positive.")
    beat_s = 60.0 / bpm
    beats: list[dict[str, Any]] = []
    strong: list[dict[str, Any]] = []
    idx = 0
    while True:
        t = idx * beat_s
        if t >= duration_s:
            break
        is_downbeat = idx % 4 == 0
        intensity = 1.0 if is_downbeat else (0.72 if idx % 2 == 0 else 0.52)
        beats.append({"time": round(t, 3), "intensity": intensity})
        if is_downbeat:
            strong.append({"time": round(t, 3), "intensity": 1.0, "kind": "bar_downbeat"})
        idx += 1
    return {
        "duration": round(duration_s, 3),
        "tempo": round(bpm, 2),
        "beats": beats,
        "strongCues": strong,
    }


def analyze_byo_track(audio_path: Path, output_json: Path | None = None) -> dict[str, Any]:
    """Analyzes BPM, beats, and strongCues of any BYO audio file using ephemeral `uv`."""
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio track not found: {audio_path}")
    if not shutil.which("uv"):
        raise RuntimeError("`uv` is required for ephemeral librosa beat analysis on BYO tracks.")

    worker = r'''
import json, sys
import librosa
import numpy as np

path = sys.argv[1]
y, sr = librosa.load(path, sr=22050, mono=True)
duration = float(len(y) / sr)
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 110.0
beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

max_env = float(np.max(onset_env)) if len(onset_env) else 1.0
beats = []
for f_idx, t_s in zip(beat_frames.tolist(), beat_times):
    strength = float(onset_env[min(f_idx, len(onset_env) - 1)] / max(1e-6, max_env))
    beats.append({"time": round(float(t_s), 3), "intensity": round(strength, 3)})

print(json.dumps({"duration": round(duration, 3), "tempo": round(bpm, 2), "beats": beats}))
'''
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--quiet",
            "--with",
            "librosa",
            "--with",
            "numpy",
            "--with",
            "soundfile",
            "python",
            "-c",
            worker,
            str(audio_path.resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"BYO beat analysis failed:\n{proc.stderr[-1200:]}")

    raw = json.loads(proc.stdout.strip().splitlines()[-1])
    candidates = [(b["time"], b["intensity"]) for b in raw.get("beats", [])]
    raw["strongCues"] = pick_strong_cues(candidates, min_gap_s=1.2, max_cues=32)

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze BPM and strong cues of a BYO music track.")
    parser.add_argument("audio_file", type=Path, help="Path to MP3/WAV/OGG track.")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON path.")
    args = parser.parse_args()

    result = analyze_byo_track(args.audio_file, output_json=args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
