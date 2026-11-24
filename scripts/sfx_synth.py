#!/usr/bin/env python3
"""DemoCraft procedural DSP SFX synthesizer (100% Python stdlib, 0 MB repo weight).

Generates clean, duration-matched transition and UI sound effects (`whoosh`,
`riser`, `laser_tech`, `pop`, `click`, `sub_drop`, `success_chime`) using
filtered noise, pitch envelopes, and harmonic partials — zero external deps
and zero licensing restrictions.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import random
import wave
from pathlib import Path
from typing import Any

SAMPLE_RATE = 32000
SFX_PRESETS = (
    "whoosh",
    "riser",
    "laser_tech",
    "pop",
    "click",
    "sub_drop",
    "success_chime",
)


def _write_mono_wav(samples: list[float], output_path: Path, sample_rate: int = SAMPLE_RATE) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(s) for s in samples), default=1.0)
    norm = 0.88 / peak if peak > 1e-6 else 1.0
    pcm = array.array(
        "h",
        (max(-32767, min(32767, int(math.tanh(s * norm) * 32767))) for s in samples),
    )
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _synth_whoosh(n: int, rng: random.Random) -> list[float]:
    out: list[float] = []
    lp = 0.0
    hp_prev = 0.0
    for i in range(n):
        p = i / max(1, n - 1)
        # Smooth bell envelope peaking at 55%
        env = math.sin(math.pi * (p ** 0.85)) ** 1.6
        cutoff = 0.04 + 0.34 * (math.sin(math.pi * p) ** 1.3)
        noise = rng.uniform(-1.0, 1.0)
        lp = lp + cutoff * (noise - lp)
        bp = lp - hp_prev * 0.65
        hp_prev = lp
        # Subtle pitched air undertone
        tone = 0.14 * math.sin(2.0 * math.pi * (140.0 + 180.0 * math.sin(math.pi * p)) * (i / SAMPLE_RATE))
        out.append((bp * 1.4 + tone) * env)
    return out


def _synth_riser(n: int, rng: random.Random) -> list[float]:
    out: list[float] = []
    lp = 0.0
    phase1 = 0.0
    phase2 = 0.0
    for i in range(n):
        p = i / max(1, n - 1)
        env = (p ** 1.8) * (1.0 - max(0.0, (p - 0.92) / 0.08))
        freq = 160.0 * (2.0 ** (2.2 * p))
        phase1 += 2.0 * math.pi * freq / SAMPLE_RATE
        phase2 += 2.0 * math.pi * (freq * 1.5) / SAMPLE_RATE
        noise = rng.uniform(-1.0, 1.0)
        alpha = 0.03 + 0.42 * (p ** 2)
        lp = lp + alpha * (noise - lp)
        val = 0.45 * math.sin(phase1) + 0.25 * math.sin(phase2) + 0.65 * lp
        out.append(val * env)
    return out


def _synth_laser_tech(n: int) -> list[float]:
    out: list[float] = []
    phase = 0.0
    fm_phase = 0.0
    for i in range(n):
        p = i / max(1, n - 1)
        attack = min(1.0, i / (SAMPLE_RATE * 0.008))
        decay = math.exp(-5.2 * p)
        env = attack * decay
        freq = 220.0 + 1650.0 * math.exp(-7.5 * p)
        fm_phase += 2.0 * math.pi * (freq * 2.01) / SAMPLE_RATE
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        val = math.sin(phase + 0.45 * math.sin(fm_phase) * (1.0 - p))
        out.append(val * env)
    return out


def _synth_pop(n: int) -> list[float]:
    out: list[float] = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        env = min(1.0, t / 0.004) * math.exp(-t * 28.0)
        freq = 190.0 + 340.0 * math.exp(-t * 40.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        out.append((math.sin(phase) + 0.2 * math.sin(2.0 * phase)) * env)
    return out


def _synth_click(n: int, rng: random.Random) -> list[float]:
    out: list[float] = []
    lp = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 140.0)
        noise = rng.uniform(-1.0, 1.0)
        lp = lp + 0.45 * (noise - lp)
        tone = math.sin(2.0 * math.pi * 1650.0 * t) * math.exp(-t * 190.0)
        out.append((0.6 * lp + 0.5 * tone) * env)
    return out


def _synth_sub_drop(n: int) -> list[float]:
    out: list[float] = []
    phase = 0.0
    for i in range(n):
        p = i / max(1, n - 1)
        attack = min(1.0, i / (SAMPLE_RATE * 0.006))
        env = attack * math.exp(-3.4 * p)
        freq = 38.0 + 92.0 * math.exp(-6.0 * p)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        out.append(math.tanh(1.6 * math.sin(phase)) * env)
    return out


def _synth_success_chime(n: int) -> list[float]:
    # Warm Cmaj9 glassy arpeggio (C5, E5, G5, D6)
    notes = [(0.0, 523.25), (0.055, 659.25), (0.11, 783.99), (0.17, 1174.66)]
    out = [0.0] * n
    for onset_s, freq in notes:
        start_i = int(onset_s * SAMPLE_RATE)
        for i in range(start_i, n):
            dt = (i - start_i) / SAMPLE_RATE
            env = min(1.0, dt / 0.008) * math.exp(-dt * 4.8)
            val = (
                0.65 * math.sin(2.0 * math.pi * freq * dt)
                + 0.25 * math.sin(2.0 * math.pi * (freq * 2.0) * dt) * math.exp(-dt * 8.0)
                + 0.10 * math.sin(2.0 * math.pi * (freq * 3.0) * dt) * math.exp(-dt * 12.0)
            )
            out[i] += val * env
    return out


def generate_sfx(
    preset: str,
    output_path: Path,
    duration_s: float = 0.4,
    seed: int = 42,
) -> dict[str, Any]:
    """Synthesizes a clean mono WAV SFX for the given preset and duration."""
    key = preset.strip().lower()
    if key not in SFX_PRESETS:
        raise ValueError(
            f"Unsupported SFX preset '{preset}'. Choose from: {', '.join(SFX_PRESETS)}."
        )
    if not (0.05 <= duration_s <= 4.0):
        raise ValueError(f"Duration must be between 0.05 and 4.0 seconds, got {duration_s}.")

    n = max(1, int(round(duration_s * SAMPLE_RATE)))
    rng = random.Random(seed)

    if key == "whoosh":
        samples = _synth_whoosh(n, rng)
    elif key == "riser":
        samples = _synth_riser(n, rng)
    elif key == "laser_tech":
        samples = _synth_laser_tech(n)
    elif key == "pop":
        samples = _synth_pop(n)
    elif key == "click":
        samples = _synth_click(n, rng)
    elif key == "sub_drop":
        samples = _synth_sub_drop(n)
    else:
        samples = _synth_success_chime(n)

    _write_mono_wav(samples, output_path, sample_rate=SAMPLE_RATE)
    return {
        "preset": key,
        "output_path": str(output_path),
        "duration_s": round(n / SAMPLE_RATE, 3),
        "sample_rate": SAMPLE_RATE,
        "size_kb": round(output_path.stat().st_size / 1024.0, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize procedural DemoCraft SFX WAV.")
    parser.add_argument("preset", choices=SFX_PRESETS, help="SFX preset name.")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output WAV path.")
    parser.add_argument("--duration", type=float, default=0.4, help="Duration in seconds.")
    args = parser.parse_args()

    meta = generate_sfx(args.preset, args.output, duration_s=args.duration)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
