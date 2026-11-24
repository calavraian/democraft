#!/usr/bin/env python3
"""DemoCraft 3-layer FFmpeg audio mixer with auto-ducking (stdlib only).

Mixes:
  1. Background music (bundled procedural bed OR BYO track) with smooth
     fade-in/fade-out and automatic sidechain ducking whenever voiceover speaks.
  2. Timed SFX cues (bundled CC0 Kenney/typing pack, procedural `sfx_synth.py`,
     or BYO audio files).
  3. Optional voiceover track (Gemini 3.8 TTS, Kokoro fallback, or BYO).

Uses the same zero-bloat FFmpeg runner (`system` -> `uv` -> `docker`) from
`encode_video.py`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from encode_video import resolve_ffmpeg_strategy, run_ffmpeg

BUNDLED_SFX_DIR = Path(__file__).resolve().parents[1] / "assets" / "audio" / "sfx"


@dataclass(frozen=True)
class SfxEvent:
    """Single timed sound effect placement."""

    path: Path
    at_s: float
    volume: float = 0.35


def resolve_sfx_reference(ref: str) -> Path:
    """Resolves either a local file path or a relative bundled CC0 SFX reference."""
    direct = Path(ref)
    if direct.is_file():
        return direct.resolve()
    bundled = (BUNDLED_SFX_DIR / ref).resolve()
    if bundled.is_file():
        return bundled
    raise FileNotFoundError(
        f"SFX file not found: '{ref}' (checked path and bundled CC0 library at {BUNDLED_SFX_DIR})."
    )


def build_mix_args(
    output_path: Path,
    duration_s: float,
    music_path: Path | None = None,
    voice_path: Path | None = None,
    sfx_events: list[SfxEvent] | None = None,
    music_volume: float = 0.38,
    duck_volume: float = 0.19,
    sfx_scale: float = 1.0,
    voice_delay_s: float = 0.25,
    fade_out_s: float = 1.4,
) -> list[str]:
    """Builds deterministic FFmpeg filter_complex arguments for 3-layer mixing."""
    events = sfx_events or []
    if music_path is None and voice_path is None and not events:
        raise ValueError("Audio mixer requires at least one audio source (music, voice, or SFX).")
    if duration_s <= 0:
        raise ValueError(f"Duration must be positive, got {duration_s}.")

    args: list[str] = ["-y"]
    filters: list[str] = []
    mix_labels: list[str] = []
    input_idx = 0

    music_idx: int | None = None
    voice_idx: int | None = None

    if music_path is not None:
        music_idx = input_idx
        args.extend(["-stream_loop", "-1", "-i", str(music_path)])
        input_idx += 1

    if voice_path is not None:
        voice_idx = input_idx
        args.extend(["-i", str(voice_path)])
        input_idx += 1

    sfx_inputs: list[tuple[int, SfxEvent]] = []
    for ev in events:
        args.extend(["-i", str(ev.path)])
        sfx_inputs.append((input_idx, ev))
        input_idx += 1

    fade_start = max(0.0, duration_s - fade_out_s)

    # Voice preparation (splits into main mix + sidechain trigger when music is present)
    if voice_idx is not None:
        v_delay_ms = max(0, int(round(voice_delay_s * 1000)))
        voice_chain = (
            f"[{voice_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"adelay={v_delay_ms}|{v_delay_ms},volume=1.0,apad=whole_dur={duration_s:.3f},"
            f"atrim=0:{duration_s:.3f}"
        )
        if music_idx is not None:
            filters.append(f"{voice_chain},asplit=2[vo_main][vo_sc]")
        else:
            filters.append(f"{voice_chain}[vo_main]")
        mix_labels.append("[vo_main]")

    # Music preparation with smooth fades + automatic sidechain ducking under voice
    if music_idx is not None:
        m_base = (
            f"[{music_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{duration_s:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.45,afade=t=out:st={fade_start:.3f}:d={fade_out_s:.3f},"
            f"volume={music_volume:.3f}"
        )
        if voice_idx is not None:
            ratio = max(2.0, min(10.0, music_volume / max(0.04, duck_volume)))
            filters.append(f"{m_base}[mus_pre]")
            filters.append(
                f"[mus_pre][vo_sc]sidechaincompress=threshold=0.02:ratio={ratio:.2f}:"
                "attack=25:release=380:makeup=1[mus_ducked]"
            )
            mix_labels.append("[mus_ducked]")
        else:
            filters.append(f"{m_base}[mus_clean]")
            mix_labels.append("[mus_clean]")

    # Timed SFX placements (kept subtle under voiceover via sfx_scale)
    for s_idx, ev in sfx_inputs:
        delay_ms = max(0, int(round(ev.at_s * 1000)))
        effective_vol = max(0.0, ev.volume * sfx_scale)
        lbl = f"[sfx_{s_idx}]"
        filters.append(
            f"[{s_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume={effective_vol:.3f},adelay={delay_ms}|{delay_ms},"
            f"apad=whole_dur={duration_s:.3f},atrim=0:{duration_s:.3f}{lbl}"
        )
        mix_labels.append(lbl)

    if len(mix_labels) == 1:
        filters.append(f"{mix_labels[0]}alimiter=limit=0.95[mix_out]")
    else:
        joined = "".join(mix_labels)
        filters.append(
            f"{joined}amix=inputs={len(mix_labels)}:duration=first:normalize=0,"
            "alimiter=limit=0.95[mix_out]"
        )

    args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[mix_out]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output_path),
        ]
    )
    return args


def load_sfx_cue_list(cues_path: Path) -> list[SfxEvent]:
    """Loads a JSON array of `{"sfx": "...", "at_s": 1.2, "volume": 0.35}` events."""
    raw = json.loads(cues_path.read_text(encoding="utf-8"))
    items = raw.get("sfx", raw) if isinstance(raw, dict) else raw
    events: list[SfxEvent] = []
    for item in items:
        events.append(
            SfxEvent(
                path=resolve_sfx_reference(str(item["sfx"])),
                at_s=float(item["at_s"]),
                volume=float(item.get("volume", 0.35)),
            )
        )
    return events


def mix_audio_tracks(
    output_path: Path,
    duration_s: float,
    music_path: Path | None = None,
    voice_path: Path | None = None,
    sfx_events: list[SfxEvent] | None = None,
    music_volume: float = 0.38,
    duck_volume: float = 0.19,
    sfx_scale: float = 1.0,
    voice_delay_s: float = 0.25,
) -> dict[str, Any]:
    """Renders the final mixed stereo WAV using zero-bloat FFmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    strategy = resolve_ffmpeg_strategy()
    args = build_mix_args(
        output_path=output_path,
        duration_s=duration_s,
        music_path=music_path,
        voice_path=voice_path,
        sfx_events=sfx_events,
        music_volume=music_volume,
        duck_volume=duck_volume,
        sfx_scale=sfx_scale,
        voice_delay_s=voice_delay_s,
    )
    run_ffmpeg(args, strategy=strategy)
    return {
        "strategy": strategy,
        "output_wav": str(output_path),
        "duration_s": round(duration_s, 2),
        "has_music": music_path is not None,
        "has_voice": voice_path is not None,
        "sfx_count": len(sfx_events or []),
        "size_kb": round(output_path.stat().st_size / 1024.0, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix music, timed SFX, and voiceover via FFmpeg.")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output mixed WAV path.")
    parser.add_argument("--duration", type=float, required=True, help="Total mix duration (s).")
    parser.add_argument("--music", type=Path, default=None, help="Background music track (WAV/MP3).")
    parser.add_argument("--voice", type=Path, default=None, help="Voiceover track (WAV/MP3).")
    parser.add_argument("--sfx-cues", type=Path, default=None, help="JSON list of timed SFX cues.")
    parser.add_argument("--music-volume", type=float, default=0.38)
    parser.add_argument("--duck-volume", type=float, default=0.19)
    parser.add_argument("--sfx-scale", type=float, default=1.0, help="Global multiplier for SFX levels (e.g. 0.55 under voice).")
    parser.add_argument("--voice-delay", type=float, default=0.25)
    args = parser.parse_args()

    events = load_sfx_cue_list(args.sfx_cues) if args.sfx_cues else []
    summary = mix_audio_tracks(
        output_path=args.output,
        duration_s=args.duration,
        music_path=args.music,
        voice_path=args.voice,
        sfx_events=events,
        music_volume=args.music_volume,
        duck_volume=args.duck_volume,
        sfx_scale=args.sfx_scale,
        voice_delay_s=args.voice_delay,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
