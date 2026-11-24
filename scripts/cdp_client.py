#!/usr/bin/env python3
"""Shared pure-stdlib Chrome DevTools Protocol (CDP) & headless Chrome manager.

Reused by both `render_frames.py` (deterministic composition capture) and
`capture_flow.py` (declarative live web app navigation & hybrid capture).
Zero external pip dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from probe import find_chromium_browser

WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_localhost_url(url: str) -> bool:
    """Returns True only for http(s) URLs targeting local loopback interfaces."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host in LOOPBACK_HOSTS


def encode_ws_client_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """Encodes a single FIN=1 masked RFC 6455 client WebSocket frame."""
    header = bytearray([0x80 | (opcode & 0x0F)])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))

    mask_key = os.urandom(4)
    header.extend(mask_key)
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + masked


def decode_ws_frame_from_bytes(raw: bytes) -> tuple[int, bytes]:
    """Decodes a single RFC 6455 frame from an in-memory buffer."""
    if len(raw) < 2:
        raise ValueError("Truncated WebSocket frame header.")
    opcode = raw[0] & 0x0F
    masked = bool(raw[1] & 0x80)
    length = raw[1] & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", raw[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", raw[offset : offset + 8])[0]
        offset += 8
    mask_key = b""
    if masked:
        mask_key = raw[offset : offset + 4]
        offset += 4
    payload = raw[offset : offset + length]
    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Unexpected EOF while reading from CDP WebSocket.")
        buf.extend(chunk)
    return bytes(buf)


class MinimalCDPClient:
    """Pure-stdlib RFC 6455 WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._msg_id = 0
        self._handshake(host, port, path)

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(req.encode("ascii"))

        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = self._sock.recv(1024)
            if not chunk:
                raise ConnectionError("CDP WebSocket handshake closed unexpectedly.")
            response.extend(chunk)

        header_text = response.split(b"\r\n\r\n", 1)[0].decode("ascii", errors="replace")
        if "101" not in header_text.splitlines()[0]:
            raise ConnectionError(f"CDP WebSocket upgrade failed: {header_text}")

        expected_accept = base64.b64encode(
            hashlib.sha1((key + WS_MAGIC_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept not in header_text:
            raise ConnectionError("Invalid Sec-WebSocket-Accept header from Chrome CDP.")

    def _read_message(self) -> str:
        chunks: list[bytes] = []
        while True:
            b1, b2 = _recv_exact(self._sock, 2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", _recv_exact(self._sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _recv_exact(self._sock, 8))[0]
            mask_key = _recv_exact(self._sock, 4) if masked else b""
            payload = _recv_exact(self._sock, length)
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == 0x9:  # PING -> PONG
                self._sock.sendall(encode_ws_client_frame(payload, opcode=0xA))
                continue
            if opcode == 0x8:  # CLOSE
                raise ConnectionError("Chrome CDP closed the WebSocket connection.")
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8")

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._msg_id += 1
        req_id = self._msg_id
        body = json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8")
        self._sock.sendall(encode_ws_client_frame(body, opcode=0x1))

        while True:
            msg = json.loads(self._read_message())
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                return msg.get("result", {})

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def find_free_port() -> int:
    """Allocates an unused TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_page_ws(cdp_port: int, timeout: float = 15.0) -> str:
    """Polls Chrome's local debugging endpoint until a page WebSocket URL is ready."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{cdp_port}/json/list"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
                for target in targets:
                    if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                        return str(target["webSocketDebuggerUrl"])
        except Exception:
            pass
        time.sleep(0.15)
    raise TimeoutError(f"Timed out waiting for headless browser CDP endpoint on port {cdp_port}.")


class ChromeSession:
    """Context manager managing a clean, ephemeral headless Chrome CDP session."""

    def __init__(
        self,
        width: int,
        height: int,
        device_scale_factor: float = 1.0,
        mobile: bool = False,
        browser_path: str | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.device_scale_factor = device_scale_factor
        self.mobile = mobile
        self.browser_path = browser_path or find_chromium_browser()
        self._profile_dir: Path | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self.cdp: MinimalCDPClient | None = None

    def __enter__(self) -> MinimalCDPClient:
        if not self.browser_path:
            raise RuntimeError(
                "No Chromium-based browser found. Install Google Chrome/Chromium or set DEMOCRAFT_BROWSER."
            )

        cdp_port = find_free_port()
        self._profile_dir = Path(tempfile.mkdtemp(prefix="democraft_chrome_"))
        cmd = [
            self.browser_path,
            "--headless=new",
            f"--remote-debugging-port={cdp_port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self._profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            f"--window-size={self.width},{self.height}",
            f"--force-device-scale-factor={self.device_scale_factor}",
            "about:blank",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        ws_url = wait_for_page_ws(cdp_port)
        self.cdp = MinimalCDPClient(ws_url)
        self.cdp.call("Page.enable")
        self.cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self.width,
                "height": self.height,
                "deviceScaleFactor": self.device_scale_factor,
                "mobile": self.mobile,
            },
        )
        return self.cdp

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.cdp is not None:
            self.cdp.close()
        if self._proc is not None:
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self._proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self._proc.wait(timeout=2)
        if self._profile_dir is not None:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
