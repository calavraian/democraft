"""Unit tests for DemoCraft zero-bloat FFmpeg video encoder (`encode_video.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import encode_video


def test_resolve_runner_prefers_system_then_uv_then_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # System preferred
    monkeypatch.setattr(
        encode_video.shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in ("ffmpeg", "uv", "docker") else None,
    )
    assert encode_video.resolve_ffmpeg_strategy() == "system"

    # uv fallback when ffmpeg missing
    monkeypatch.setattr(
        encode_video.shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in ("uv", "docker") else None,
    )
    assert encode_video.resolve_ffmpeg_strategy() == "uv"

    # docker fallback when ffmpeg & uv missing
    monkeypatch.setattr(
        encode_video.shutil,
        "which",
        lambda cmd: "/usr/bin/docker" if cmd == "docker" else None,
    )
    assert encode_video.resolve_ffmpeg_strategy() == "docker"

    # none raises RuntimeError
    monkeypatch.setattr(encode_video.shutil, "which", lambda cmd: None)
    with pytest.raises(RuntimeError, match="No FFmpeg runner available"):
        encode_video.resolve_ffmpeg_strategy()


def test_build_encode_args_includes_yuv420p_and_faststart(tmp_path: Path) -> None:
    # Arrange
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    out_mp4 = tmp_path / "demo.mp4"

    # Act
    args = encode_video.build_encode_args(
        frames_dir=frames_dir,
        output_path=out_mp4,
        fps=30,
        audio_path=None,
    )

    # Assert
    assert "-pix_fmt" in args
    assert "yuv420p" in args
    assert "+faststart" in args
    assert str(frames_dir / "frame_%05d.png") in args
    assert str(out_mp4) == args[-1]


def test_build_encode_args_with_optional_audio(tmp_path: Path) -> None:
    # Arrange
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    audio_file = tmp_path / "track.mp3"
    audio_file.write_bytes(b"fake")
    out_mp4 = tmp_path / "demo.mp4"

    # Act
    args = encode_video.build_encode_args(
        frames_dir=frames_dir,
        output_path=out_mp4,
        fps=30,
        audio_path=audio_file,
    )

    # Assert
    assert str(audio_file) in args
    assert "-shortest" in args
    assert "aac" in args


def test_build_frame0_bake_args_replaces_only_frame_zero(tmp_path: Path) -> None:
    # Arrange
    raw_mp4 = tmp_path / "raw.mp4"
    poster_jpg = tmp_path / "poster.jpg"
    final_mp4 = tmp_path / "final.mp4"

    # Act
    args = encode_video.build_frame0_bake_args(
        input_video=raw_mp4,
        poster_image=poster_jpg,
        output_video=final_mp4,
    )

    # Assert
    assert "-filter_complex" in args
    fc = args[args.index("-filter_complex") + 1]
    assert "enable='eq(n,0)'" in fc
    assert str(final_mp4) == args[-1]


def test_validate_frames_dir_rejects_empty_or_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        encode_video.validate_frames_dir(tmp_path / "does_not_exist")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="No PNG frames found"):
        encode_video.validate_frames_dir(empty_dir)


def test_cleanup_work_artifacts_keep_editable_prunes_derived_and_keeps_sources(tmp_path: Path) -> None:
    work = tmp_path / "work"
    frames = work / "frames"
    stills = work / "stills"
    comp = work / "composition"
    for d in (frames, stills, comp):
        d.mkdir(parents=True)
    (frames / "frame_00000.png").write_bytes(b"png")
    (stills / "still_00.png").write_bytes(b"png")
    (comp / "index.html").write_text("<html></html>", encoding="utf-8")
    (work / "storyboard.json").write_text("{}", encoding="utf-8")
    (work / "sfx_cues.json").write_text("[]", encoding="utf-8")
    (work / "voice.wav").write_bytes(b"paid-tts")
    (work / "mix.wav").write_bytes(b"derived-mix")
    (work / "music.wav").write_bytes(b"regenerable-music")
    (work / "music.beats.json").write_text("{}", encoding="utf-8")
    (work / "captions.json").write_text("{}", encoding="utf-8")
    (work / "whoosh_soft.wav").write_bytes(b"regenerable-sfx")

    report = encode_video.cleanup_work_artifacts(
        frames_dir=frames, mode="keep-editable", audio_path=work / "mix.wav"
    )

    assert report["mode"] == "keep-editable"
    # Heavy/regenerable files removed
    assert not frames.exists()
    assert not stills.exists()
    assert not (work / "mix.wav").exists()
    assert not (work / "music.wav").exists()
    assert not (work / "music.beats.json").exists()
    assert not (work / "captions.json").exists()
    assert not (work / "whoosh_soft.wav").exists()
    # Paid TTS & editable blueprints preserved!
    assert (work / "voice.wav").exists()
    assert (work / "storyboard.json").exists()
    assert (work / "sfx_cues.json").exists()
    assert (comp / "index.html").exists()


def test_cleanup_work_artifacts_all_removes_entire_work_directory(tmp_path: Path) -> None:
    work = tmp_path / "work"
    frames = work / "frames"
    frames.mkdir(parents=True)
    (frames / "frame_00000.png").write_bytes(b"png")
    (work / "voice.wav").write_bytes(b"wav")
    final_mp4 = tmp_path / "demo.mp4"
    final_mp4.write_bytes(b"mp4")

    report = encode_video.cleanup_work_artifacts(frames_dir=frames, mode="all")

    assert report["mode"] == "all"
    assert not work.exists()
    assert final_mp4.exists()
