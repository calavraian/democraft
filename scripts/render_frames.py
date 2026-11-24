#!/usr/bin/env python3
"""DemoCraft deterministic Chrome CDP frame renderer (100% Python stdlib).

Drives an already-installed Chromium-based browser via shared `cdp_client.py`
— zero Playwright, zero npm/npx, zero external pip dependencies.
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

from captions import cues_to_dicts, load_captions
from cdp_client import (
    ChromeSession,
    decode_ws_frame_from_bytes,
    encode_ws_client_frame,
)

FORMAT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
}

__all__ = [
    "FORMAT_DIMENSIONS",
    "build_timestamps",
    "decode_ws_frame_from_bytes",
    "encode_ws_client_frame",
    "render_composition",
    "resolve_dimensions",
]


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

    width, height = resolve_dimensions(fmt)
    timestamps = build_timestamps(duration, fps, stills=stills)
    out_dir.mkdir(parents=True, exist_ok=True)

    caption_payload: list[dict[str, Any]] | None = None
    if captions_path is not None:
        caption_payload = cues_to_dicts(load_captions(captions_path, lang=lang))

    server, http_port = _start_static_server(html_path.parent)
    written: list[Path] = []

    try:
        with ChromeSession(width=width, height=height, device_scale_factor=1.0) as cdp:
            page_url = f"http://127.0.0.1:{http_port}/{urllib.parse.quote(html_path.name)}"
            cdp.call("Page.navigate", {"url": page_url})

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
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render deterministic frames via Chrome CDP.")
    parser.add_argument("html_path", type=Path, help="Path to composition index.html.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for PNGs.")
    parser.add_argument("--format", choices=("landscape", "vertical", "square"), default="vertical")
    parser.add_argument("--duration", type=float, required=True, help="Total duration in seconds.")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30).")
    parser.add_argument("--stills", default=None, help="Comma-separated timestamps for QA stills.")
    parser.add_argument("--captions", type=Path, default=None, help="Optional captions/storyboard JSON.")
    parser.add_argument("--lang", default=None, help="Language code inside captions/storyboard.")
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
