#!/usr/bin/env python3
"""DemoCraft multi-mood procedural music bed generator (100% Python stdlib).

Synthesizes warm, stereo, royalty-free (public-domain) background music beds
in 4 curated commercial & tutorial moods with exact beat/strongCue metadata:
  - `ambient-calm`     (80 BPM)  : Peaceful stereo pads & soft shimmer (tutorials)
  - `harmonic-simple`  (96 BPM)  : Warm electric-piano chords & gentle pulse (polished SaaS)
  - `modern-clean`     (114 BPM) : Crisp upbeat commercial groove & plucked chords (promos)
  - `tech-spectacular` (124 BPM) : Energetic electro-synth drive & pulsing bass (launches)
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

from analyze_beats import build_regular_beat_grid

SAMPLE_RATE = 32000

# MIDI note helper -> frequency Hz
def _midi_hz(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


MOOD_SPECS: dict[str, dict[str, Any]] = {
    "ambient-calm": {
        "bpm": 80,
        "chords": [
            [48, 55, 60, 64, 71, 74],  # Cmaj9
            [45, 52, 57, 60, 67, 71],  # Am9
            [41, 48, 53, 57, 64, 67],  # Fmaj9
            [43, 50, 55, 59, 64, 67],  # G6
        ],
        "kick": False,
        "hat": False,
        "snare": False,
        "arp": "slow_shimmer",
        "pad_gain": 0.42,
        "bass_gain": 0.22,
    },
    "harmonic-simple": {
        "bpm": 96,
        "chords": [
            [41, 53, 57, 60, 64],  # Fmaj7
            [43, 55, 59, 62, 64],  # G6
            [40, 52, 55, 59, 62],  # Em7
            [45, 57, 60, 64, 67],  # Am7
        ],
        "kick": True,
        "hat": True,
        "snare": False,
        "arp": "warm_ep",
        "pad_gain": 0.28,
        "bass_gain": 0.28,
    },
    "modern-clean": {
        "bpm": 114,
        "chords": [
            [50, 57, 62, 66, 69, 73],  # Dmaj7
            [45, 52, 57, 61, 64, 66],  # A6
            [47, 54, 59, 62, 66, 69],  # Bm7
            [43, 50, 55, 59, 62, 66],  # Gmaj7
        ],
        "kick": True,
        "hat": True,
        "snare": True,
        "arp": "modern_pluck",
        "pad_gain": 0.24,
        "bass_gain": 0.34,
    },
    "tech-spectacular": {
        "bpm": 124,
        "chords": [
            [45, 52, 57, 60, 64, 71],  # Am9
            [41, 48, 53, 57, 60, 64],  # Fmaj7
            [48, 55, 60, 64, 67, 74],  # Cmaj9
            [43, 50, 55, 60, 62, 67],  # Gsus4
        ],
        "kick": True,
        "hat": True,
        "snare": True,
        "arp": "electro_pulse",
        "pad_gain": 0.30,
        "bass_gain": 0.38,
    },
}


def _add_kick(left: list[float], right: list[float], start_i: int, gain: float) -> None:
    dur_n = int(0.19 * SAMPLE_RATE)
    end_i = min(len(left), start_i + dur_n)
    phase = 0.0
    for i in range(start_i, end_i):
        dt = (i - start_i) / SAMPLE_RATE
        env = min(1.0, dt / 0.003) * math.exp(-dt * 19.0)
        freq = 44.0 + 105.0 * math.exp(-dt * 36.0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        s = math.tanh(1.4 * math.sin(phase)) * env * gain
        left[i] += s
        right[i] += s


def _add_hat(
    left: list[float],
    right: list[float],
    start_i: int,
    gain: float,
    pan: float,
    rng: random.Random,
) -> None:
    dur_n = int(0.045 * SAMPLE_RATE)
    end_i = min(len(left), start_i + dur_n)
    prev = 0.0
    g_l = gain * (1.0 - max(0.0, pan))
    g_r = gain * (1.0 + min(0.0, pan))
    for i in range(start_i, end_i):
        dt = (i - start_i) / SAMPLE_RATE
        env = math.exp(-dt * 85.0)
        n_raw = rng.uniform(-1.0, 1.0)
        hp = n_raw - 0.85 * prev
        prev = n_raw
        s = hp * env
        left[i] += s * g_l
        right[i] += s * g_r


def _add_snare(
    left: list[float],
    right: list[float],
    start_i: int,
    gain: float,
    rng: random.Random,
) -> None:
    dur_n = int(0.14 * SAMPLE_RATE)
    end_i = min(len(left), start_i + dur_n)
    lp = 0.0
    for i in range(start_i, end_i):
        dt = (i - start_i) / SAMPLE_RATE
        env_n = math.exp(-dt * 28.0)
        env_t = math.exp(-dt * 42.0)
        lp = lp + 0.35 * (rng.uniform(-1.0, 1.0) - lp)
        body = math.sin(2.0 * math.pi * (185.0 + 60.0 * math.exp(-dt * 30.0)) * dt) * env_t
        s = (0.65 * lp * env_n + 0.45 * body) * gain
        left[i] += s
        right[i] += s


def _add_pluck_note(
    left: list[float],
    right: list[float],
    start_i: int,
    freq: float,
    dur_s: float,
    gain: float,
    pan: float,
    warmth: float = 0.35,
) -> None:
    dur_n = int(dur_s * SAMPLE_RATE)
    end_i = min(len(left), start_i + dur_n)
    g_l = gain * (0.75 - 0.25 * pan)
    g_r = gain * (0.75 + 0.25 * pan)
    two_pi = 2.0 * math.pi
    for i in range(start_i, end_i):
        dt = (i - start_i) / SAMPLE_RATE
        att = min(1.0, dt / 0.008)
        dec = math.exp(-dt * (3.6 / max(0.25, dur_s)))
        bright = math.exp(-dt * 9.5)
        sig = (
            0.72 * math.sin(two_pi * freq * dt)
            + warmth * math.sin(two_pi * (freq * 2.0) * dt) * bright
            + (warmth * 0.4) * math.sin(two_pi * (freq * 3.0) * dt) * bright * bright
        )
        v = sig * att * dec
        left[i] += v * g_l
        right[i] += v * g_r


def _apply_stereo_reverb_and_master(
    left: list[float],
    right: list[float],
    fade_in_s: float = 0.6,
    fade_out_s: float = 1.6,
) -> tuple[list[float], list[float]]:
    n = len(left)
    delay_l = int(0.165 * SAMPLE_RATE)
    delay_r = int(0.221 * SAMPLE_RATE)
    wet_l = [0.0] * n
    wet_r = [0.0] * n
    lp_l = 0.0
    lp_r = 0.0

    for i in range(n):
        fb_l = wet_r[i - delay_l] * 0.30 if i >= delay_l else 0.0
        fb_r = wet_l[i - delay_r] * 0.30 if i >= delay_r else 0.0
        lp_l = lp_l + 0.28 * ((left[i] + fb_l) - lp_l)
        lp_r = lp_r + 0.28 * ((right[i] + fb_r) - lp_r)
        wet_l[i] = lp_l
        wet_r[i] = lp_r

    out_l = [left[i] * 0.82 + wet_l[i] * 0.28 for i in range(n)]
    out_r = [right[i] * 0.82 + wet_r[i] * 0.28 for i in range(n)]

    # Smooth fade-in and fade-out
    fin_n = min(n, int(fade_in_s * SAMPLE_RATE))
    fout_n = min(n, int(fade_out_s * SAMPLE_RATE))
    for i in range(fin_n):
        g = i / max(1, fin_n)
        out_l[i] *= g
        out_r[i] *= g
    for i in range(fout_n):
        idx = n - 1 - i
        g = i / max(1, fout_n)
        out_l[idx] *= g
        out_r[idx] *= g

    peak = max(max((abs(v) for v in out_l), default=1.0), max((abs(v) for v in out_r), default=1.0))
    scale = 0.86 / peak if peak > 1e-6 else 1.0
    return (
        [math.tanh(v * scale) for v in out_l],
        [math.tanh(v * scale) for v in out_r],
    )


def generate_music_bed(
    mood: str,
    duration_s: float,
    output_wav: Path,
    output_beats_json: Path | None = None,
    seed: int = 101,
) -> dict[str, Any]:
    """Synthesizes a stereo multi-mood harmonic music bed WAV + exact beat grid JSON."""
    key = mood.strip().lower()
    if key not in MOOD_SPECS:
        raise ValueError(
            f"Unsupported mood '{mood}'. Choose from: {', '.join(MOOD_SPECS)}."
        )
    if duration_s <= 0:
        raise ValueError(f"Duration must be positive, got {duration_s}.")

    spec = MOOD_SPECS[key]
    bpm = int(spec["bpm"])
    beat_s = 60.0 / bpm
    bar_s = beat_s * 4.0
    n = max(1, int(round(duration_s * SAMPLE_RATE)))

    left = [0.0] * n
    right = [0.0] * n
    rng = random.Random(seed)
    chords: list[list[int]] = spec["chords"]
    two_pi = 2.0 * math.pi

    # 1. Warm detuned stereo pad & rounded bassline per bar
    num_bars = int(math.ceil(duration_s / bar_s))
    for bar in range(num_bars):
        chord = chords[bar % len(chords)]
        bar_start_s = bar * bar_s
        bar_end_s = min(duration_s, bar_start_s + bar_s)
        s_i = int(bar_start_s * SAMPLE_RATE)
        e_i = min(n, int(bar_end_s * SAMPLE_RATE))
        bass_hz = _midi_hz(chord[0])
        pad_freqs = [_midi_hz(m) for m in chord[1:]]
        pad_gain = float(spec["pad_gain"]) / max(1, len(pad_freqs))
        bass_gain = float(spec["bass_gain"])

        for i in range(s_i, e_i):
            dt = (i - s_i) / SAMPLE_RATE
            bar_pos = dt / bar_s
            pad_env = min(1.0, dt / 0.35) * min(1.0, max(0.0, (bar_s - dt) / 0.25))
            # Gentle sidechain breathing on beat for modern/tech moods
            if spec["kick"]:
                beat_phase = (dt % beat_s) / beat_s
                duck = 0.65 + 0.35 * min(1.0, beat_phase / 0.28)
            else:
                duck = 0.88 + 0.12 * math.sin(two_pi * bar_pos)

            pl = 0.0
            pr = 0.0
            for idx_f, f in enumerate(pad_freqs):
                detune = 1.0022 if idx_f % 2 == 0 else 0.9978
                pl += math.sin(two_pi * f * dt) + 0.22 * math.sin(two_pi * f * 2.0 * dt)
                pr += math.sin(two_pi * (f * detune) * dt) + 0.22 * math.sin(two_pi * f * 2.0 * dt)

            bass_env = min(1.0, dt / 0.04) * math.exp(-dt * (0.45 if key != "tech-spectacular" else 0.15))
            bass_v = (
                math.sin(two_pi * bass_hz * dt)
                + 0.28 * math.sin(two_pi * (bass_hz * 2.0) * dt)
            ) * bass_env * bass_gain * duck

            left[i] += pl * pad_gain * pad_env * duck + bass_v
            right[i] += pr * pad_gain * pad_env * duck + bass_v

        # 2. Rhythmic melodic layer & percussion inside each bar
        arp_mode = spec["arp"]
        steps_per_bar = 16 if arp_mode == "electro_pulse" else 8
        step_s = bar_s / steps_per_bar
        for step in range(steps_per_bar):
            t_step = bar_start_s + step * step_s
            if t_step >= duration_s:
                break
            idx_step = int(t_step * SAMPLE_RATE)

            if arp_mode == "slow_shimmer" and step in (0, 4):
                note_midi = chord[2 + ((bar + step) % (len(chord) - 2))] + 12
                _add_pluck_note(left, right, idx_step, _midi_hz(note_midi), 1.4, 0.14, pan=0.4 if step == 0 else -0.4, warmth=0.2)
            elif arp_mode == "warm_ep" and step in (0, 2, 3, 5, 6):
                note_midi = chord[1 + ((step + bar) % (len(chord) - 1))]
                _add_pluck_note(left, right, idx_step, _midi_hz(note_midi), 0.75, 0.22, pan=-0.35 if step % 2 == 0 else 0.35, warmth=0.35)
            elif arp_mode == "modern_pluck" and step in (0, 2, 3, 5, 7):
                note_midi = chord[1 + ((step * 2 + bar) % (len(chord) - 1))]
                _add_pluck_note(left, right, idx_step, _midi_hz(note_midi), 0.45, 0.24, pan=-0.45 if step % 2 == 0 else 0.45, warmth=0.48)
            elif arp_mode == "electro_pulse":
                # Energetic 16th-note pulse on bass octave + upper arpeggio
                if step % 2 == 0:
                    note_midi = chord[1 + ((step // 2 + bar) % (len(chord) - 1))]
                    _add_pluck_note(left, right, idx_step, _midi_hz(note_midi), 0.28, 0.23, pan=-0.5 if (step // 2) % 2 == 0 else 0.5, warmth=0.58)
                else:
                    _add_pluck_note(left, right, idx_step, _midi_hz(chord[0] + 12), 0.18, 0.16, pan=0.0, warmth=0.45)

        # Percussion on 4 beats per bar
        for beat in range(4):
            t_beat = bar_start_s + beat * beat_s
            if t_beat >= duration_s:
                break
            b_i = int(t_beat * SAMPLE_RATE)
            if spec["kick"] and (beat in (0, 2) or (key == "tech-spectacular" and beat in (0, 1, 2, 3))):
                _add_kick(left, right, b_i, gain=0.48 if key != "harmonic-simple" else 0.30)
            if spec["snare"] and beat in (1, 3):
                _add_snare(left, right, b_i, gain=0.22 if key == "modern-clean" else 0.28, rng=rng)
            if spec["hat"]:
                off_i = int((t_beat + beat_s * 0.5) * SAMPLE_RATE)
                if off_i < n:
                    _add_hat(left, right, off_i, gain=0.14, pan=0.25 if beat % 2 == 0 else -0.25, rng=rng)

    master_l, master_r = _apply_stereo_reverb_and_master(left, right)

    interleaved = array.array("h")
    for l_val, r_val in zip(master_l, master_r):
        interleaved.append(max(-32767, min(32767, int(l_val * 32767))))
        interleaved.append(max(-32767, min(32767, int(r_val * 32767))))

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(interleaved.tobytes())

    beat_data = build_regular_beat_grid(bpm=float(bpm), duration_s=duration_s)
    beat_data["mood"] = key
    if output_beats_json is not None:
        output_beats_json.parent.mkdir(parents=True, exist_ok=True)
        output_beats_json.write_text(json.dumps(beat_data, indent=2), encoding="utf-8")

    return {
        "mood": key,
        "bpm": bpm,
        "duration_s": round(duration_s, 2),
        "output_wav": str(output_wav),
        "output_beats_json": str(output_beats_json) if output_beats_json else None,
        "size_kb": round(output_wav.stat().st_size / 1024.0, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate royalty-free multi-mood DemoCraft music bed.")
    parser.add_argument("mood", choices=tuple(MOOD_SPECS.keys()), help="Musical mood preset.")
    parser.add_argument("--duration", type=float, required=True, help="Target duration in seconds.")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output stereo WAV path.")
    parser.add_argument("--beats-out", type=Path, default=None, help="Optional beats JSON output path.")
    args = parser.parse_args()

    meta = generate_music_bed(
        mood=args.mood,
        duration_s=args.duration,
        output_wav=args.output,
        output_beats_json=args.beats_out,
    )
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
