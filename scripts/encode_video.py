#!/usr/bin/env python3
"""DemoCraft zero-bloat FFmpeg encoder with Frame-0 poster baking (stdlib only).

Automatically selects the lightest available FFmpeg runner:
  1. System `ffmpeg` on PATH
  2. Ephemeral `uv run --with imageio-ffmpeg` (zero global OS installs)
  3. Ephemeral `docker run --rm` fallback
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DOCKER_FFMPEG_IMAGE = "jrottenberg/ffmpeg:6.1-alpine"


def resolve_ffmpeg_strategy() -> str:
    """Returns the preferred available FFmpeg execution strategy."""
    if shutil.which("ffmpeg"):
        return "system"
    if shutil.which("uv"):
        return "uv"
    if shutil.which("docker"):
        return "docker"
    raise RuntimeError(
        "No FFmpeg runner available. Install ffmpeg, uv, or docker to encode MP4."
    )


def validate_frames_dir(frames_dir: Path) -> list[Path]:
    """Verifies that `frames_dir` exists and contains numbered PNG frames."""
    if not frames_dir.is_dir():
        raise FileNotFoundError(f"Frames directory does not exist: {frames_dir}")
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise ValueError(f"No PNG frames found in {frames_dir} (expected frame_00000.png ...).")
    return frames


def build_encode_args(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    audio_path: Path | None = None,
) -> list[str]:
    """Builds FFmpeg arguments for deterministic H.264 yuv420p encoding."""
    args = [
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
    ]
    if audio_path is not None:
        args.extend(["-i", str(audio_path)])

    args.extend(
        [
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
    )
    if audio_path is not None:
        args.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

    args.append(str(output_path))
    return args


def build_poster_extract_args(
    input_video: Path,
    poster_time: float,
    poster_image: Path,
) -> list[str]:
    """Builds FFmpeg arguments to extract a single high-quality poster JPEG."""
    return [
        "-y",
        "-ss",
        f"{poster_time:.3f}",
        "-i",
        str(input_video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(poster_image),
    ]


def build_frame0_bake_args(
    input_video: Path,
    poster_image: Path,
    output_video: Path,
) -> list[str]:
    """Builds FFmpeg arguments replacing ONLY frame 0 with the settled poster image."""
    return [
        "-y",
        "-i",
        str(input_video),
        "-i",
        str(poster_image),
        "-filter_complex",
        "[0:v][1:v]overlay=0:0:enable='eq(n,0)',format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_video),
    ]


def run_ffmpeg(ffmpeg_args: list[str], strategy: str | None = None) -> None:
    """Executes FFmpeg arguments using the resolved zero-bloat strategy."""
    chosen = strategy or resolve_ffmpeg_strategy()

    if chosen == "system":
        cmd = ["ffmpeg", *ffmpeg_args]
    elif chosen == "uv":
        shim = (
            "import imageio_ffmpeg, subprocess, sys; "
            "sys.exit(subprocess.call([imageio_ffmpeg.get_ffmpeg_exe(), *sys.argv[1:]]))"
        )
        cmd = ["uv", "run", "--quiet", "--with", "imageio-ffmpeg", "python", "-c", shim, *ffmpeg_args]
    elif chosen == "docker":
        # Map host paths under a shared root into /work inside the ephemeral container.
        host_paths = [Path(a).resolve() for a in ffmpeg_args if "/" in a and not a.startswith("-")]
        common_root = Path(os.path.commonpath([str(p.parent) for p in host_paths]))
        mapped_args: list[str] = []
        for arg in ffmpeg_args:
            if "/" in arg and not arg.startswith("-"):
                rel = Path(arg).resolve().relative_to(common_root)
                mapped_args.append(f"/work/{rel.as_posix()}")
            else:
                mapped_args.append(arg)
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{common_root}:/work",
            DOCKER_FFMPEG_IMAGE,
            *mapped_args,
        ]
    else:
        raise ValueError(f"Unknown FFmpeg strategy: {chosen}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg ({chosen}) failed with exit code {result.returncode}:\n{result.stderr[-1200:]}"
        )


PRESERVED_EDITABLE_WAVS = {"voice.wav"}
DISPOSABLE_WORK_FILES = {"mix.wav", "music.wav", "music.beats.json", "captions.json"}


def cleanup_work_artifacts(
    frames_dir: Path,
    mode: str = "none",
    audio_path: Path | None = None,
) -> dict[str, object]:
    """Reclaims disk space after successful MP4 encoding without touching final deliverables.

    Modes:
      - `none`          : Keep all intermediates.
      - `frames`        : Delete only the heavy raw PNG `frames_dir`.
      - `keep-editable` : Delete `frames/`, sibling `stills/`, derived `mix.wav`, regenerable
                          `music.wav`/beats/procedural SFX WAVs; preserve `voice.wav`,
                          blueprints (`storyboard.json`, `flow.json`, `sfx_cues.json`), and `composition/`.
      - `all`           : Delete the entire `work/` parent folder (or `frames_dir`), leaving
                          strictly the final deliverables (`demo.mp4`, `poster.jpg`, `.srt`, copy).
    """
    chosen = mode.strip().lower()
    if chosen not in ("none", "frames", "keep-editable", "all"):
        raise ValueError(f"Unsupported clean-work mode '{mode}'. Choose none|frames|keep-editable|all.")

    removed: list[str] = []
    if chosen == "none":
        return {"mode": chosen, "removed": removed}

    resolved_frames = frames_dir.resolve()
    work_dir = resolved_frames.parent

    if chosen == "all":
        target = work_dir if work_dir.name == "work" else resolved_frames
        if target.exists():
            shutil.rmtree(target)
            removed.append(str(target))
        return {"mode": chosen, "removed": removed}

    if resolved_frames.exists():
        shutil.rmtree(resolved_frames)
        removed.append(str(resolved_frames))

    if chosen == "frames":
        return {"mode": chosen, "removed": removed}

    # mode == "keep-editable"
    stills_dir = work_dir / "stills"
    if stills_dir.is_dir():
        shutil.rmtree(stills_dir)
        removed.append(str(stills_dir))

    if audio_path is not None:
        resolved_audio = audio_path.resolve()
        if resolved_audio.is_file() and resolved_audio.parent == work_dir and resolved_audio.name not in PRESERVED_EDITABLE_WAVS:
            resolved_audio.unlink()
            removed.append(str(resolved_audio))

    for fname in DISPOSABLE_WORK_FILES:
        candidate = work_dir / fname
        if candidate.is_file():
            candidate.unlink()
            removed.append(str(candidate))

    # Remove regenerable procedural SFX WAVs (e.g. whoosh_soft.wav) while keeping voice.wav
    if work_dir.is_dir():
        for wav in sorted(work_dir.glob("*.wav")):
            if wav.name not in PRESERVED_EDITABLE_WAVS:
                wav.unlink()
                removed.append(str(wav))

    return {"mode": chosen, "removed": removed}


def encode_demo_video(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    poster_time: float | None = None,
    poster_out: Path | None = None,
    audio_path: Path | None = None,
    clean_work: str = "none",
) -> dict[str, object]:
    """Encodes PNG frames into MP4 and optionally extracts + bakes Frame-0 poster."""
    frames = validate_frames_dir(frames_dir)
    if audio_path is not None and not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    strategy = resolve_ffmpeg_strategy()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if poster_time is None:
        run_ffmpeg(build_encode_args(frames_dir, output_path, fps=fps, audio_path=audio_path), strategy)
        summary: dict[str, object] = {
            "strategy": strategy,
            "frames": len(frames),
            "fps": fps,
            "output_mp4": str(output_path),
            "poster_jpg": None,
            "size_kb": round(output_path.stat().st_size / 1024.0, 1),
        }
    else:
        poster_target = poster_out or output_path.with_suffix(".jpg")
        poster_target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="democraft_encode_") as tmp:
            raw_mp4 = Path(tmp) / "raw.mp4"
            run_ffmpeg(build_encode_args(frames_dir, raw_mp4, fps=fps, audio_path=audio_path), strategy)
            run_ffmpeg(build_poster_extract_args(raw_mp4, poster_time, poster_target), strategy)
            run_ffmpeg(build_frame0_bake_args(raw_mp4, poster_target, output_path), strategy)

        summary = {
            "strategy": strategy,
            "frames": len(frames),
            "fps": fps,
            "duration_seconds": round(len(frames) / fps, 2),
            "output_mp4": str(output_path),
            "poster_jpg": str(poster_target),
            "poster_time": poster_time,
            "size_kb": round(output_path.stat().st_size / 1024.0, 1),
        }

    if clean_work != "none" and output_path.is_file() and output_path.stat().st_size > 0:
        summary["cleanup"] = cleanup_work_artifacts(
            frames_dir=frames_dir, mode=clean_work, audio_path=audio_path
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Encode DemoCraft PNG frames to H.264 MP4.")
    parser.add_argument("frames_dir", type=Path, help="Directory with frame_00000.png ...")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Target .mp4 path.")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30).")
    parser.add_argument("--poster-time", type=float, default=None, help="Timestamp (s) to bake as Frame 0.")
    parser.add_argument("--poster-out", type=Path, default=None, help="Optional poster .jpg path.")
    parser.add_argument("--audio", type=Path, default=None, help="Optional BYO audio track.")
    parser.add_argument(
        "--clean-work",
        choices=("none", "frames", "keep-editable", "all"),
        default="none",
        help="Auto-cleanup intermediates after MP4 succeeds (recommended: keep-editable).",
    )
    args = parser.parse_args()

    summary = encode_demo_video(
        frames_dir=args.frames_dir,
        output_path=args.output,
        fps=args.fps,
        poster_time=args.poster_time,
        poster_out=args.poster_out,
        audio_path=args.audio,
        clean_work=args.clean_work,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
