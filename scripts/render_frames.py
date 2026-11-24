#!/usr/bin/env python3
"""DemoCraft deterministic Chrome CDP frame renderer (100% Python stdlib).

Drives an already-installed Chromium-based browser via Chrome DevTools Protocol
over a lightweight RFC 6455 WebSocket client — zero Playwright, zero npm/npx,
zero external pip dependencies.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from captions import cues_to_dicts, load_captions
from probe import find_chromium_browser

FORMAT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
}

WS_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def resolve_dimensions(fmt: str) -> tuple[int, int]:
    """Resolves a named video format into (width, height) pixels."""
    normalized = fmt.strip().lower()
    if normalized not in FORMAT_DIMENSIONS:
        raise ValueError(
            f"Unsupported format '{fmt}'. Choose from: {', '.join(FORMAT_DIMENSIONS)}."
        )
    return FORMAT_DIMENSIONS[normalized]


def build_timestamps(
    duration: float,
    fps: int,
    stills: str | None = None,
) -> list[float]:
    """Computes deterministic frame timestamps for full renders or QA stills."""
    if duration <= 0:
        raise ValueError(f"Duration must be positive, got {duration}.")
    if fps <= 0:
        raise ValueError(f"FPS must be positive, got {fps}.")

    if stills is not None:
        parsed: list[float] = []
        for token in stills.split(","):
            raw = token.strip()
            if not raw:
                continue
            val = float(raw)
            if val < 0 or val > duration:
                raise ValueError(f"Still timestamp {val}s is out of range [0, {duration}].")
            parsed.append(round(val, 4))
        if not parsed:
            raise ValueError("No valid timestamps found in --stills.")
        return parsed

    total_frames = max(1, int(round(duration * fps)))
    return [round(i / fps, 6) for i in range(total_frames)]


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
    """Decodes a single RFC 6455 frame from an in-memory buffer (for testing/helpers)."""
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
    """Pure-stdlib WebSocket client for Chrome DevTools Protocol."""

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

            if opcode == 0x9:  # PING -> reply PONG
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


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_static_server(root_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root_dir), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _wait_for_page_ws(cdp_port: int, timeout: float = 15.0) -> str:
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


def render_composition(
    html_path: Path,
    out_dir: Path,
    fmt: str,
    duration: float,
    fps: int,
    stills: str | None = None,
    captions_path: Path | None = None,
    lang: str | None = None,
    safe_zone_overlay: bool = False,
) -> list[Path]:
    """Renders deterministic PNG frames or QA stills from a DemoCraft HTML composition."""
    if not html_path.is_file():
        raise FileNotFoundError(f"Composition HTML not found: {html_path}")

    browser = find_chromium_browser()
    if not browser:
        raise RuntimeError(
            "No Chromium-based browser found. Install Google Chrome/Chromium or set DEMOCRAFT_BROWSER."
        )

    width, height = resolve_dimensions(fmt)
    timestamps = build_timestamps(duration, fps, stills=stills)
    out_dir.mkdir(parents=True, exist_ok=True)

    caption_payload: list[dict[str, Any]] | None = None
    if captions_path is not None:
        caption_payload = cues_to_dicts(load_captions(captions_path, lang=lang))

    server, http_port = _start_static_server(html_path.parent)
    cdp_port = _find_free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="democraft_chrome_"))
    chrome_proc: subprocess.Popen[bytes] | None = None
    cdp: MinimalCDPClient | None = None
    written: list[Path] = []

    try:
        chrome_cmd = [
            browser,
            "--headless=new",
            f"--remote-debugging-port={cdp_port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            "--mute-audio",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            "about:blank",
        ]
        chrome_proc = subprocess.Popen(
            chrome_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        ws_url = _wait_for_page_ws(cdp_port)
        cdp = MinimalCDPClient(ws_url)
        cdp.call("Page.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

        page_url = f"http://127.0.0.1:{http_port}/{urllib.parse.quote(html_path.name)}"
        cdp.call("Page.navigate", {"url": page_url})

        # Wait for full load, fonts, and all <img> elements to decode.
        ready_js = """
        (async () => {
          if (document.readyState !== 'complete') {
            await new Promise(res => window.addEventListener('load', res, { once: true }));
          }
          if (document.fonts && document.fonts.ready) {
            await document.fonts.ready;
          }
          const imgs = Array.from(document.images || []);
          await Promise.all(imgs.map(img => img.complete ? Promise.resolve() : new Promise(res => {
            img.addEventListener('load', res, { once: true });
            img.addEventListener('error', res, { once: true });
          })));
          return typeof window.__DEMOCRAFT_SEEK__ === 'function';
        })()
        """
        eval_res = cdp.call(
            "Runtime.evaluate",
            {"expression": ready_js, "awaitPromise": True, "returnByValue": True},
        )
        if not eval_res.get("result", {}).get("value"):
            raise RuntimeError(
                "Composition must define `window.__DEMOCRAFT_SEEK__(t)` (see composition-contract.md)."
            )

        if caption_payload is not None:
            cap_json = json.dumps(caption_payload, ensure_ascii=False)
            cdp.call(
                "Runtime.evaluate",
                {
                    "expression": f"window.__DEMOCRAFT_SET_CAPTIONS__ && window.__DEMOCRAFT_SET_CAPTIONS__({cap_json})",
                    "returnByValue": True,
                },
            )

        if safe_zone_overlay:
            cdp.call(
                "Runtime.evaluate",
                {
                    "expression": "window.__DEMOCRAFT_TOGGLE_SAFE_ZONES__ && window.__DEMOCRAFT_TOGGLE_SAFE_ZONES__(true)",
                    "returnByValue": True,
                },
            )

        is_stills = stills is not None
        for idx, ts in enumerate(timestamps):
            seek_js = (
                f"Promise.resolve(window.__DEMOCRAFT_SEEK__({ts:.6f}))"
                ".then(() => new Promise(r => requestAnimationFrame(r)))"
            )
            cdp.call(
                "Runtime.evaluate",
                {"expression": seek_js, "awaitPromise": True, "returnByValue": True},
            )
            shot = cdp.call(
                "Page.captureScreenshot",
                {"format": "png", "fromSurface": True, "optimizeForSpeed": True},
            )
            png_bytes = base64.b64decode(shot["data"])
            filename = f"still_{idx:02d}_{ts:05.2f}s.png" if is_stills else f"frame_{idx:05d}.png"
            out_file = out_dir / filename
            out_file.write_bytes(png_bytes)
            written.append(out_file)

        return written
    finally:
        if cdp is not None:
            cdp.close()
        if chrome_proc is not None:
            try:
                os.killpg(chrome_proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                chrome_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(chrome_proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                chrome_proc.wait(timeout=2)
        server.shutdown()
        server.server_close()
        shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render deterministic frames via Chrome CDP.")
    parser.add_argument("html_path", type=Path, help="Path to composition index.html.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for PNGs.")
    parser.add_argument("--format", choices=("landscape", "vertical", "square"), default="vertical")
    parser.add_argument("--duration", type=float, required=True, help="Total duration in seconds.")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30).")
    parser.add_argument("--stills", default=None, help="Comma-separated timestamps for QA stills.")
    parser.add_argument("--captions", type=Path, default=None, help="Optional captions.json path.")
    parser.add_argument("--lang", default=None, help="Language code inside captions.json.")
    parser.add_argument("--safe-zone-overlay", action="store_true", help="Enable QA safe zones.")
    args = parser.parse_args()

    t0 = time.perf_counter()
    files = render_composition(
        html_path=args.html_path,
        out_dir=args.out_dir,
        fmt=args.format,
        duration=args.duration,
        fps=args.fps,
        stills=args.stills,
        captions_path=args.captions,
        lang=args.lang,
        safe_zone_overlay=args.safe_zone_overlay,
    )
    elapsed = time.perf_counter() - t0
    print(
        json.dumps(
            {
                "rendered_count": len(files),
                "out_dir": str(args.out_dir),
                "elapsed_seconds": round(elapsed, 2),
                "mode": "stills" if args.stills is not None else "frames",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
