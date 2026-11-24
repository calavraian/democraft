"""Unit tests for DemoCraft 3-layer FFmpeg audio mixer (`audio_mixer.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audio_mixer


def test_build_mix_args_with_music_voice_auto_ducking_and_sfx(tmp_path: Path) -> None:
    # Arrange
    music = tmp_path / "music.wav"
    voice = tmp_path / "voice.wav"
    sfx1 = tmp_path / "click.ogg"
    sfx2 = tmp_path / "whoosh.wav"
    for p in (music, voice, sfx1, sfx2):
        p.write_bytes(b"stub")
    out_mix = tmp_path / "mix.wav"

    sfx_events = [
        audio_mixer.SfxEvent(path=sfx1, at_s=2.5, volume=0.7),
        audio_mixer.SfxEvent(path=sfx2, at_s=6.0, volume=0.6),
    ]

    # Act
    args = audio_mixer.build_mix_args(
        output_path=out_mix,
        duration_s=18.0,
        music_path=music,
        voice_path=voice,
        sfx_events=sfx_events,
        music_volume=0.38,
        duck_volume=0.19,
        sfx_scale=0.5,
    )

    # Assert
    assert "-filter_complex" in args
    fc = args[args.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc
    assert "volume=0.350" in fc  # 0.7 * 0.5 sfx_scale
    assert "adelay=2500|2500" in fc
    assert "adelay=6000|6000" in fc
    assert "amix=" in fc
    assert str(out_mix) == args[-1]


def test_build_mix_args_music_only_without_voice_skips_ducking(tmp_path: Path) -> None:
    music = tmp_path / "music.wav"
    music.write_bytes(b"stub")
    out_mix = tmp_path / "mix.wav"

    args = audio_mixer.build_mix_args(
        output_path=out_mix,
        duration_s=16.0,
        music_path=music,
        voice_path=None,
        sfx_events=[],
    )

    fc = args[args.index("-filter_complex") + 1]
    assert "sidechaincompress" not in fc
    assert "afade=t=out" in fc


def test_resolve_sfx_reference_finds_bundled_cc0_asset() -> None:
    resolved = audio_mixer.resolve_sfx_reference("ui/click_001.ogg")
    assert resolved.is_file()
    assert resolved.name == "click_001.ogg"


def test_build_mix_args_rejects_empty_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one audio source"):
        audio_mixer.build_mix_args(
            output_path=tmp_path / "empty.wav",
            duration_s=10.0,
            music_path=None,
            voice_path=None,
            sfx_events=[],
        )
