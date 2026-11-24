"""Unit tests for shared DemoCraft Chrome CDP client (`cdp_client.py`)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cdp_client


def test_is_localhost_url_allows_loopback_and_rejects_remote() -> None:
    assert cdp_client.is_localhost_url("http://localhost:3000") is True
    assert cdp_client.is_localhost_url("http://127.0.0.1:8000/attendance") is True
    assert cdp_client.is_localhost_url("https://[::1]:3000/") is True
    assert cdp_client.is_localhost_url("https://example.com") is False
    assert cdp_client.is_localhost_url("http://192.168.1.50:3000") is False
    assert cdp_client.is_localhost_url("file:///etc/passwd") is False


def test_websocket_frame_roundtrip_all_length_tiers() -> None:
    for size in (16, 400, 70000):
        payload = ("B" * size).encode("utf-8")
        encoded = cdp_client.encode_ws_client_frame(payload)
        assert encoded[0] == 0x81
        assert (encoded[1] & 0x80) == 0x80

        opcode, decoded = cdp_client.decode_ws_frame_from_bytes(encoded)
        assert opcode == 0x1
        assert decoded == payload


def test_decode_unmasked_64bit_server_frame() -> None:
    payload = b"z" * 70000
    frame = bytes([0x81, 127]) + struct.pack("!Q", len(payload)) + payload
    opcode, decoded = cdp_client.decode_ws_frame_from_bytes(frame)
    assert opcode == 0x1
    assert decoded == payload
