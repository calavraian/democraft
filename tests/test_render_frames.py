"""Unit tests for DemoCraft deterministic Chrome CDP renderer (`render_frames.py`)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import render_frames


def test_resolve_dimensions_all_supported_formats() -> None:
    assert render_frames.resolve_dimensions("landscape") == (1920, 1080)
    assert render_frames.resolve_dimensions("vertical") == (1080, 1920)
    assert render_frames.resolve_dimensions("square") == (1080, 1080)

    with pytest.raises(ValueError, match="Unsupported format"):
        render_frames.resolve_dimensions("ultrawide")


def test_build_timestamps_full_render() -> None:
    # Arrange & Act
    timestamps = render_frames.build_timestamps(duration=2.0, fps=10, stills=None)
    # Assert
    assert len(timestamps) == 20
    assert timestamps[0] == 0.0
    assert pytest.approx(timestamps[-1], abs=1e-6) == 1.9


def test_build_timestamps_stills_mode() -> None:
    # Arrange & Act
    timestamps = render_frames.build_timestamps(duration=18.0, fps=30, stills="0, 2.5, 9.0, 17.5")
    # Assert
    assert timestamps == [0.0, 2.5, 9.0, 17.5]


def test_build_timestamps_rejects_out_of_range_stills() -> None:
    with pytest.raises(ValueError, match="out of range"):
        render_frames.build_timestamps(duration=10.0, fps=30, stills="0,12.5")


def test_websocket_frame_encode_and_decode_roundtrip() -> None:
    # Arrange: test short (<126), medium (126..65535), and large (>65535) payloads
    for size in (12, 300, 70000):
        payload = ("A" * size).encode("utf-8")
        encoded = render_frames.encode_ws_client_frame(payload)

        # Verify client frame has FIN=1, text opcode=1, and MASK bit=1
        assert encoded[0] == 0x81
        assert (encoded[1] & 0x80) == 0x80

        # Decode masked client frame back to original bytes
        opcode, decoded = render_frames.decode_ws_frame_from_bytes(encoded)
        assert opcode == 0x1
        assert decoded == payload


def test_decode_unmasked_server_frame() -> None:
    # Arrange: craft an unmasked server text frame
    payload = b'{"id":1,"result":{"data":"abc"}}'
    frame = bytes([0x81, len(payload)]) + payload

    # Act
    opcode, decoded = render_frames.decode_ws_frame_from_bytes(frame)

    # Assert
    assert opcode == 0x1
    assert decoded == payload


def test_decode_extended_64bit_server_frame() -> None:
    # Arrange: craft unmasked server frame with 64-bit length header
    payload = b"x" * 70000
    header = bytes([0x81, 127]) + struct.pack("!Q", len(payload))

    # Act
    opcode, decoded = render_frames.decode_ws_frame_from_bytes(header + payload)

    # Assert
    assert opcode == 0x1
    assert decoded == payload
