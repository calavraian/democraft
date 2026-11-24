#!/usr/bin/env python3
"""DemoCraft declarative web navigation & hybrid live capture runner (stdlib only).

Automates real user journeys against a local (or explicitly opted-in remote)
web app via Chrome DevTools Protocol (`cdp_client.py`) — zero Playwright, zero
npx, zero global installs.

Supports hybrid capture:
  - High-res Retina step screenshots (`capture`) with automatic normalized
    element bounding-box extraction (`captures.json`) for highlights & taps.
  - Smooth eased real-scroll frame sequences (`record_scroll`) for authentic
    demo and tutorial walkthroughs.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

from cdp_client import ChromeSession, is_localhost_url

VIEWPORT_PRESETS: dict[str, tuple[int, int]] = {
    "desktop": (1440, 900),
    "hd": (1280, 720),
    "mobile": (390, 844),
    "vertical": (1080, 1920),
    "landscape": (1920, 1080),
    "square": (1080, 1080),
}

SUPPORTED_ACTIONS = {
    "goto",
    "wait_for",
    "click",
    "click_text",
    "type",
    "scroll",
    "pause",
    "capture",
    "record_scroll",
    "record_drag",
}

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")
CSS_RGB_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)"
)
FALLBACK_HIGHLIGHT_PALETTE = ("#18181B", "#0284C7", "#D97706", "#E11D48")


def parse_css_rgb(raw: str | None) -> tuple[int, int, int] | None:
    """Parses a computed CSS `rgb(...)` or `rgba(...)` string, ignoring transparent values."""
    if not raw:
        return None
    m = CSS_RGB_RE.search(str(raw))
    if not m:
        return None
    alpha = float(m.group(4)) if m.group(4) is not None else 1.0
    if alpha < 0.25:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Formats an (R, G, B) tuple as uppercase `#RRGGBB`."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.lstrip("#")
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def _lin(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _wcag_contrast(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1 = _relative_luminance(c1)
    l2 = _relative_luminance(c2)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    # Redmean weighted perceptual RGB distance (0..~765)
    rmean = (c1[0] + c2[0]) / 2.0
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    return math.sqrt(
        (2.0 + rmean / 256.0) * dr * dr
        + 4.0 * dg * dg
        + (2.0 + (255.0 - rmean) / 256.0) * db * db
    )


def _color_saturation(rgb: tuple[int, int, int]) -> float:
    hi = max(rgb)
    lo = min(rgb)
    return 0.0 if hi == 0 else (hi - lo) / hi


def recommend_highlight_color(
    scene_palette_hex: list[str],
    target_bg_hexes: list[str],
) -> dict[str, Any]:
    """Selects ONE consistent highlight color recycled from the scene's own palette.

    Evaluates worst-case perceptual separation + WCAG contrast across all captured
    target button backgrounds so the highlight never blends into a matching button
    and never shifts into a rainbow across steps.
    """
    unique_scene = list(dict.fromkeys(c.upper() for c in scene_palette_hex if c.startswith("#") and len(c) == 7))
    candidates = unique_scene if unique_scene else list(FALLBACK_HIGHLIGHT_PALETTE)
    source = "scene_palette" if unique_scene else "fallback"

    target_rgbs = [
        _hex_to_rgb(h) for h in target_bg_hexes if isinstance(h, str) and h.startswith("#") and len(h) == 7
    ]
    if not target_rgbs:
        target_rgbs = [(245, 243, 236)]  # light canvas default

    best_hex = candidates[0]
    best_score = -1.0
    best_min_contrast = 1.0

    for rank_idx, cand_hex in enumerate(candidates):
        cand_rgb = _hex_to_rgb(cand_hex)
        # Skip near-white candidates (they disappear on light surfaces and merge with inner white ring)
        if _relative_luminance(cand_rgb) > 0.72:
            continue
        min_dist = min(_color_distance(cand_rgb, tb) for tb in target_rgbs)
        min_contrast = min(_wcag_contrast(cand_rgb, tb) for tb in target_rgbs)
        # Prefer prominent colors already common in the app; deprioritize alert/destructive reds
        prominence = max(0.65, 1.0 - 0.06 * rank_idx)
        is_alert_red = cand_rgb[0] > 185 and cand_rgb[1] < 75 and cand_rgb[2] < 100
        alert_factor = 0.72 if is_alert_red else 1.0
        chroma_bonus = 1.0 + 0.22 * _color_saturation(cand_rgb)
        score = (
            (min_dist / 765.0)
            * (0.6 + 0.4 * min(min_contrast / 4.5, 1.5))
            * chroma_bonus
            * prominence
            * alert_factor
        )
        if score > best_score:
            best_score = score
            best_hex = cand_hex
            best_min_contrast = min_contrast

    return {
        "recommended_hex": best_hex,
        "source": source,
        "min_contrast": round(best_min_contrast, 2),
        "ring_style": "dual-ring-spotlight",
        "scene_palette": unique_scene,
        "target_backgrounds": list(dict.fromkeys(h.upper() for h in target_bg_hexes if h)),
    }


def resolve_viewport(preset: str | list[int] | tuple[int, int]) -> tuple[int, int]:
    """Resolves a named viewport preset or `[width, height]` pair into CSS pixels."""
    if isinstance(preset, (list, tuple)) and len(preset) == 2:
        w, h = int(preset[0]), int(preset[1])
        if w <= 0 or h <= 0:
            raise ValueError(f"Viewport dimensions must be positive, got {preset}.")
        return (w, h)
    key = str(preset).strip().lower()
    if key not in VIEWPORT_PRESETS:
        raise ValueError(
            f"Unsupported viewport '{preset}'. Choose from: {', '.join(VIEWPORT_PRESETS)} or [w, h]."
        )
    return VIEWPORT_PRESETS[key]


def sanitize_name(raw: str) -> str:
    """Sanitizes a capture or recording name against path traversal."""
    cleaned = SAFE_NAME_RE.sub("_", raw).strip("_")
    if not cleaned:
        raise ValueError(f"Capture name cannot be empty after sanitization: '{raw}'.")
    return cleaned


def _resolve_step_url(base_url: str, step: dict[str, Any]) -> str:
    if step.get("url"):
        return str(step["url"])
    path = str(step.get("path", "/"))
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def validate_flow(flow: dict[str, Any], allow_remote: bool = False) -> None:
    """Validates flow schema, action allowlist, and localhost-first URL security."""
    if not isinstance(flow, dict):
        raise ValueError("flow.json must be a JSON object.")

    steps = flow.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        raise ValueError("Flow must define at least one step in 'steps'.")

    base_url = str(flow.get("base_url", "")).strip()
    if base_url and not allow_remote and not is_localhost_url(base_url):
        raise PermissionError(
            f"Remote base_url '{base_url}' blocked by localhost-first policy. "
            "Pass --allow-remote explicitly to capture external URLs."
        )

    resolve_viewport(flow.get("viewport", "desktop"))

    for idx, step in enumerate(steps, start=1):
        action = str(step.get("action", "")).strip().lower()
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Step #{idx}: Unsupported action '{action}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_ACTIONS))}."
            )
        if action == "goto":
            target = _resolve_step_url(base_url, step)
            if not allow_remote and not is_localhost_url(target):
                raise PermissionError(
                    f"Step #{idx}: Remote URL '{target}' blocked without --allow-remote."
                )


def normalize_rect(
    rect: dict[str, Any],
    viewport_w: int,
    viewport_h: int,
) -> dict[str, Any]:
    """Converts a CSS pixel bounding box into resolution-independent [0..1] coordinates."""
    x = max(0.0, min(1.0, float(rect["x"]) / viewport_w))
    y = max(0.0, min(1.0, float(rect["y"]) / viewport_h))
    w = max(0.0, min(1.0 - x, float(rect["width"]) / viewport_w))
    h = max(0.0, min(1.0 - y, float(rect["height"]) / viewport_h))
    cx = round(x + w / 2.0, 4)
    cy = round(y + h / 2.0, 4)
    return {
        "bounds_norm": [round(x, 4), round(y, 4), round(w, 4), round(h, 4)],
        "center_norm": [cx, cy],
        "bounds_px": [
            round(float(rect["x"]), 1),
            round(float(rect["y"]), 1),
            round(float(rect["width"]), 1),
            round(float(rect["height"]), 1),
        ],
    }


def _ease_in_out_cubic(p: float) -> float:
    p = max(0.0, min(1.0, p))
    if p < 0.5:
        return 4.0 * p * p * p
    return 1.0 - pow(-2.0 * p + 2.0, 3) / 2.0


def compute_scroll_positions(from_y: float, to_y: float, frame_count: int) -> list[float]:
    """Generates smooth easeInOutCubic scroll Y positions across `frame_count` frames."""
    if frame_count <= 1:
        return [round(to_y, 2)]
    return [
        round(from_y + (to_y - from_y) * _ease_in_out_cubic(i / (frame_count - 1)), 2)
        for i in range(frame_count)
    ]


def compute_drag_path(
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
    frame_count: int,
    arc_dy: float = 0.0,
) -> list[tuple[float, float]]:
    """Generates smooth easeInOutCubic quadratic-bezier drag coordinates across `frame_count` frames."""
    sx, sy = float(start_xy[0]), float(start_xy[1])
    ex, ey = float(end_xy[0]), float(end_xy[1])
    if frame_count <= 1:
        return [(round(ex, 2), round(ey, 2))]
    mx = (sx + ex) / 2.0
    my = (sy + ey) / 2.0 + float(arc_dy)
    pts: list[tuple[float, float]] = []
    for i in range(frame_count):
        u = _ease_in_out_cubic(i / (frame_count - 1))
        inv = 1.0 - u
        x = inv * inv * sx + 2.0 * inv * u * mx + u * u * ex
        y = inv * inv * sy + 2.0 * inv * u * my + u * u * ey
        pts.append((round(x, 2), round(y, 2)))
    return pts


def resolve_type_value(step: dict[str, Any]) -> str:
    """Resolves text to type, preferring environment variables so secrets stay off disk."""
    env_name = step.get("value_env")
    if env_name:
        val = os.getenv(str(env_name))
        if val is None:
            raise ValueError(
                f"Environment variable '{env_name}' referenced by type step is not set."
            )
        return val
    if "value" in step:
        return str(step["value"])
    raise ValueError("type step requires either 'value_env' or 'value'.")


def _eval_js(cdp: Any, expression: str, await_promise: bool = False) -> Any:
    res = cdp.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
        },
    )
    if "exceptionDetails" in res:
        raise RuntimeError(f"JS evaluation error: {res['exceptionDetails']}")
    return res.get("result", {}).get("value")


def _get_element_rect(
    cdp: Any,
    selector: str | None = None,
    text: str | None = None,
) -> dict[str, Any] | None:
    if selector:
        sel_json = json.dumps(selector)
        js = f"""
        (() => {{
          const el = document.querySelector({sel_json});
          if (!el) return null;
          const r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) return null;
          let bg = window.getComputedStyle(el).backgroundColor;
          let p = el.parentElement;
          while (p && (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {{
            bg = window.getComputedStyle(p).backgroundColor;
            p = p.parentElement;
          }}
          return {{ x: r.x, y: r.y, width: r.width, height: r.height, bg }};
        }})()
        """
        return _eval_js(cdp, js)

    if text:
        txt_json = json.dumps(text.lower())
        js = f"""
        (() => {{
          const target = {txt_json};
          const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], [role="tab"], input[type="submit"]'));
          for (const el of nodes) {{
            const content = (el.innerText || el.textContent || '').trim().toLowerCase();
            if (!content.includes(target)) continue;
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {{
              let bg = window.getComputedStyle(el).backgroundColor;
              let p = el.parentElement;
              while (p && (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {{
                bg = window.getComputedStyle(p).backgroundColor;
                p = p.parentElement;
              }}
              return {{ x: r.x, y: r.y, width: r.width, height: r.height, bg }};
            }}
          }}
          return null;
        }})()
        """
        return _eval_js(cdp, js)
    return None


def _extract_scene_palette(cdp: Any) -> list[str]:
    """Harvests distinct visible brand/UI colors already present in the captured scene."""
    js = """
    (() => {
      const counts = new Map();
      const els = document.querySelectorAll('button, a, [role="button"], [class*="badge"], span, header, aside, h1, h2');
      for (const el of Array.from(els).slice(0, 260)) {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const cs = window.getComputedStyle(el);
        for (const prop of ['backgroundColor', 'borderTopColor', 'color']) {
          const val = cs[prop];
          if (val && val !== 'rgba(0, 0, 0, 0)' && val !== 'transparent') {
            counts.set(val, (counts.get(val) || 0) + 1);
          }
        }
      }
      return Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 24)
        .map(([col]) => col);
    })()
    """
    raw_colors = _eval_js(cdp, js) or []
    palette: list[str] = []
    seen_rgbs: list[tuple[int, int, int]] = []
    for raw in raw_colors:
        rgb = parse_css_rgb(raw)
        if not rgb:
            continue
        lum = _relative_luminance(rgb)
        sat = _color_saturation(rgb)
        # Keep either distinct chromatic UI colors or deep ink accents (skip washes/whites/mid-grays)
        if lum > 0.72:
            continue
        if sat < 0.22 and lum > 0.08:
            continue
        if any(_color_distance(rgb, prev) < 75 for prev in seen_rgbs):
            continue
        seen_rgbs.append(rgb)
        palette.append(rgb_to_hex(rgb))
    return palette[:8]


def _wait_until_visible(
    cdp: Any,
    selector: str | None = None,
    text: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rect = _get_element_rect(cdp, selector=selector, text=text)
        if rect is not None:
            return rect
        time.sleep(0.15)
    target_desc = selector or f"text='{text}'"
    raise TimeoutError(f"Timed out after {timeout_s}s waiting for visible element: {target_desc}")


def _wait_page_ready(cdp: Any) -> None:
    ready_js = """
    (async () => {
      if (document.readyState !== 'complete') {
        await new Promise(res => window.addEventListener('load', res, { once: true }));
      }
      if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
      }
      return true;
    })()
    """
    _eval_js(cdp, ready_js, await_promise=True)


def _dispatch_mouse_click(cdp: Any, rect: dict[str, Any]) -> None:
    cx = float(rect["x"]) + float(rect["width"]) / 2.0
    cy = float(rect["y"]) + float(rect["height"]) / 2.0
    cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy})
    cdp.call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1},
    )
    cdp.call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1},
    )


def _capture_png(cdp: Any, out_file: Path) -> Path:
    shot = cdp.call(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "optimizeForSpeed": True},
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(base64.b64decode(shot["data"]))
    return out_file


def execute_flow_on_cdp(
    cdp: Any,
    flow: dict[str, Any],
    out_dir: Path,
    allow_remote: bool = False,
) -> dict[str, Any]:
    """Executes all declarative navigation/capture steps over an active CDP client."""
    validate_flow(flow, allow_remote=allow_remote)

    base_url = str(flow.get("base_url", "")).strip()
    viewport_spec = flow.get("viewport", "desktop")
    width, height = resolve_viewport(viewport_spec)
    device_scale = float(flow.get("device_scale", 2.0))
    out_dir.mkdir(parents=True, exist_ok=True)

    captures: list[dict[str, Any]] = []
    cues: list[dict[str, Any]] = []
    recordings: list[dict[str, Any]] = []
    scene_palette: list[str] = []
    target_bg_hexes: list[str] = []

    for idx, step in enumerate(flow["steps"], start=1):
        action = str(step["action"]).strip().lower()

        if action == "goto":
            url = _resolve_step_url(base_url, step)
            cdp.call("Page.navigate", {"url": url})
            _wait_page_ready(cdp)
            if step.get("wait_s"):
                time.sleep(float(step["wait_s"]))

        elif action == "wait_for":
            _wait_until_visible(
                cdp,
                selector=step.get("selector"),
                text=step.get("text"),
                timeout_s=float(step.get("timeout_s", 10.0)),
            )

        elif action in ("click", "click_text"):
            selector = step.get("selector") if action == "click" else None
            text = step.get("text") if action == "click_text" else None
            rect = _wait_until_visible(
                cdp,
                selector=selector,
                text=text,
                timeout_s=float(step.get("timeout_s", 10.0)),
            )
            if step.get("record_cue"):
                bg_rgb = parse_css_rgb(rect.get("bg"))
                bg_hex = rgb_to_hex(bg_rgb) if bg_rgb else None
                if bg_hex:
                    target_bg_hexes.append(bg_hex)
                cue_entry = {
                    "step": idx,
                    "kind": "click",
                    "target": selector or text,
                    **normalize_rect(rect, width, height),
                }
                if bg_hex:
                    cue_entry["background_hex"] = bg_hex
                cues.append(cue_entry)
            _dispatch_mouse_click(cdp, rect)
            if step.get("wait_s"):
                time.sleep(float(step["wait_s"]))

        elif action == "type":
            selector = str(step["selector"])
            rect = _wait_until_visible(
                cdp,
                selector=selector,
                timeout_s=float(step.get("timeout_s", 10.0)),
            )
            _dispatch_mouse_click(cdp, rect)
            # Clear input safely and insert text via CDP (never logs value)
            sel_json = json.dumps(selector)
            _eval_js(
                cdp,
                f"(() => {{ const el = document.querySelector({sel_json}); if (el) {{ el.focus(); el.select && el.select(); }} }})()",
            )
            value = resolve_type_value(step)
            cdp.call("Input.insertText", {"text": value})

        elif action == "scroll":
            container = step.get("selector")
            if step.get("to_bottom"):
                target_js = (
                    f"(() => {{ const el = document.querySelector({json.dumps(container)}); el && el.scrollTo(0, el.scrollHeight); }})()"
                    if container
                    else "window.scrollTo(0, document.documentElement.scrollHeight)"
                )
            else:
                y = float(step.get("y", 0))
                target_js = (
                    f"(() => {{ const el = document.querySelector({json.dumps(container)}); el && el.scrollTo(0, {y}); }})()"
                    if container
                    else f"window.scrollTo(0, {y})"
                )
            _eval_js(cdp, target_js)
            _eval_js(cdp, "new Promise(r => requestAnimationFrame(r))", await_promise=True)

        elif action == "pause":
            time.sleep(max(0.0, float(step.get("seconds", 0.5))))

        elif action == "capture":
            name = sanitize_name(str(step.get("name", f"step_{idx:02d}")))
            out_file = out_dir / f"{name}.png"
            _eval_js(cdp, "new Promise(r => requestAnimationFrame(r))", await_promise=True)
            _capture_png(cdp, out_file)

            for col in _extract_scene_palette(cdp):
                if col not in scene_palette:
                    scene_palette.append(col)

            entry: dict[str, Any] = {
                "step": idx,
                "name": name,
                "file": out_file.name,
                "viewport": [width, height],
                "device_scale": device_scale,
            }
            h_sel = step.get("highlight_selector")
            h_txt = step.get("highlight_text")
            if h_sel or h_txt:
                h_rect = _get_element_rect(cdp, selector=h_sel, text=h_txt)
                if h_rect is not None:
                    bg_rgb = parse_css_rgb(h_rect.get("bg"))
                    bg_hex = rgb_to_hex(bg_rgb) if bg_rgb else None
                    if bg_hex:
                        target_bg_hexes.append(bg_hex)
                    h_info = {
                        "target": h_sel or h_txt,
                        **normalize_rect(h_rect, width, height),
                    }
                    if bg_hex:
                        h_info["background_hex"] = bg_hex
                    entry["highlight"] = h_info
            captures.append(entry)

        elif action == "record_scroll":
            name = sanitize_name(str(step.get("name", f"scroll_{idx:02d}")))
            container = step.get("selector")
            duration_s = float(step.get("duration_s", 2.0))
            fps = int(step.get("fps", 15))
            frame_count = max(2, int(round(duration_s * fps)))

            if container:
                cont_json = json.dumps(container)
                bounds_js = f"""
                (() => {{
                  const el = document.querySelector({cont_json});
                  if (!el) return {{ maxY: 0, currentY: 0, mode: 'selector' }};
                  return {{ maxY: Math.max(0, el.scrollHeight - el.clientHeight), currentY: el.scrollTop, mode: 'selector' }};
                }})()
                """
            else:
                # Auto-detect whether window or an inner scrollable SPA container (e.g. <main>) scrolls
                bounds_js = """
                (() => {
                  const winMax = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
                  if (winMax >= 80) {
                    window.__DEMOCRAFT_SCROLL_EL__ = null;
                    return { maxY: winMax, currentY: window.scrollY || 0, mode: 'window' };
                  }
                  let best = null;
                  let bestMax = 0;
                  for (const el of document.querySelectorAll('main, [data-scroll], div, section')) {
                    const style = window.getComputedStyle(el);
                    if (!/(auto|scroll)/.test(style.overflowY)) continue;
                    const maxScroll = el.scrollHeight - el.clientHeight;
                    if (maxScroll > bestMax) {
                      bestMax = maxScroll;
                      best = el;
                    }
                  }
                  window.__DEMOCRAFT_SCROLL_EL__ = best;
                  if (best && bestMax > winMax) {
                    return { maxY: bestMax, currentY: best.scrollTop || 0, mode: 'auto_container' };
                  }
                  return { maxY: winMax, currentY: window.scrollY || 0, mode: 'window' };
                })()
                """

            info = _eval_js(cdp, bounds_js) or {"maxY": 0, "currentY": 0, "mode": "window"}
            scroll_mode = str(info.get("mode", "window"))
            from_y = float(step.get("from_y", info.get("currentY", 0.0)))
            if step.get("to_bottom"):
                to_y = float(info.get("maxY", from_y))
            else:
                to_y = min(float(info.get("maxY", 1e9)), float(step.get("to_y", from_y + 600)))

            positions = compute_scroll_positions(from_y, to_y, frame_count)
            seq_dir = out_dir / name
            seq_dir.mkdir(parents=True, exist_ok=True)

            for f_idx, pos_y in enumerate(positions):
                if container:
                    scroll_js = (
                        f"(() => {{ const el = document.querySelector({json.dumps(container)}); "
                        f"if (el) el.scrollTop = {pos_y}; }})()"
                    )
                elif scroll_mode == "auto_container":
                    scroll_js = f"(() => {{ if (window.__DEMOCRAFT_SCROLL_EL__) window.__DEMOCRAFT_SCROLL_EL__.scrollTop = {pos_y}; }})()"
                else:
                    scroll_js = f"window.scrollTo(0, {pos_y})"
                _eval_js(cdp, scroll_js)
                _eval_js(cdp, "new Promise(r => requestAnimationFrame(r))", await_promise=True)
                _capture_png(cdp, seq_dir / f"frame_{f_idx:05d}.png")

            recordings.append(
                {
                    "step": idx,
                    "kind": "scroll",
                    "name": name,
                    "dir": name,
                    "frames": len(positions),
                    "fps": fps,
                    "duration_s": round(len(positions) / fps, 2),
                    "from_y": round(from_y, 1),
                    "to_y": round(to_y, 1),
                    "scroll_target": container or scroll_mode,
                }
            )

        elif action == "record_drag":
            name = sanitize_name(str(step.get("name", f"drag_{idx:02d}")))
            duration_s = float(step.get("duration_s", 1.2))
            fps = int(step.get("fps", 24))
            frame_count = max(2, int(round(duration_s * fps)))
            arc_dy = float(step.get("arc_dy", 0.0))

            # Resolve start coordinate from element selector/text or explicit normalized point
            if step.get("from_norm"):
                fn = step["from_norm"]
                sx, sy = float(fn[0]) * width, float(fn[1]) * height
            else:
                src_rect = _get_element_rect(cdp, selector=step.get("selector"), text=step.get("text"))
                if src_rect is None:
                    raise RuntimeError(
                        f"Step #{idx} (record_drag): source element not found "
                        f"(selector={step.get('selector')!r}, text={step.get('text')!r})."
                    )
                sx = float(src_rect["x"]) + float(src_rect["width"]) / 2.0
                sy = float(src_rect["y"]) + float(src_rect["height"]) / 2.0

            # Resolve target coordinate from to_selector/to_text, to_norm, or dx/dy offset
            if step.get("to_selector") or step.get("to_text"):
                dst_rect = _get_element_rect(cdp, selector=step.get("to_selector"), text=step.get("to_text"))
                if dst_rect is None:
                    raise RuntimeError(f"Step #{idx} (record_drag): target drop element not found.")
                ex = float(dst_rect["x"]) + float(dst_rect["width"]) / 2.0
                ey = float(dst_rect["y"]) + float(dst_rect["height"]) / 2.0
            elif step.get("to_norm"):
                tn = step["to_norm"]
                ex, ey = float(tn[0]) * width, float(tn[1]) * height
            else:
                ex = sx + float(step.get("dx", 200.0))
                ey = sy + float(step.get("dy", 0.0))

            path_pts = compute_drag_path((sx, sy), (ex, ey), frame_count, arc_dy=arc_dy)
            seq_dir = out_dir / name
            seq_dir.mkdir(parents=True, exist_ok=True)
            pointer_frames: list[dict[str, Any]] = []

            # Real CDP pointer drag: move -> press -> interpolated drag -> release
            cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx, "y": sy, "buttons": 0})
            cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": sx, "y": sy, "button": "left", "buttons": 1, "clickCount": 1},
            )
            for f_idx, (px, py) in enumerate(path_pts):
                cdp.call(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": px, "y": py, "buttons": 1},
                )
                _eval_js(cdp, "new Promise(r => requestAnimationFrame(r))", await_promise=True)
                fname = f"frame_{f_idx:05d}.png"
                _capture_png(cdp, seq_dir / fname)
                pointer_frames.append(
                    {
                        "frame": f_idx,
                        "file": f"{name}/{fname}",
                        "cx": round(px / width, 4),
                        "cy": round(py / height, 4),
                        "state": "dragging",
                    }
                )
            cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": ex, "y": ey, "button": "left", "buttons": 0, "clickCount": 1},
            )
            _eval_js(cdp, "new Promise(r => requestAnimationFrame(r))", await_promise=True)

            recordings.append(
                {
                    "step": idx,
                    "kind": "drag",
                    "name": name,
                    "dir": name,
                    "frames": len(path_pts),
                    "fps": fps,
                    "duration_s": round(len(path_pts) / fps, 2),
                    "from_norm": [round(sx / width, 4), round(sy / height, 4)],
                    "to_norm": [round(ex / width, 4), round(ey / height, 4)],
                    "arc_norm": round(arc_dy / height, 4),
                    "pointer_frames": pointer_frames,
                }
            )

    manifest: dict[str, Any] = {
        "viewport": viewport_spec,
        "dimensions_css": [width, height],
        "device_scale": device_scale,
        "highlight_theme": recommend_highlight_color(scene_palette, target_bg_hexes),
        "captures": captures,
        "cues": cues,
        "recordings": recordings,
    }
    manifest_path = out_dir / "captures.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def run_flow_file(
    flow_path: Path,
    out_dir: Path,
    allow_remote: bool = False,
) -> dict[str, Any]:
    """Loads `flow.json`, boots headless Chrome, runs steps, and writes `captures.json`."""
    if not flow_path.is_file():
        raise FileNotFoundError(f"Flow file not found: {flow_path}")
    flow = json.loads(flow_path.read_text(encoding="utf-8"))
    validate_flow(flow, allow_remote=allow_remote)

    viewport_spec = flow.get("viewport", "desktop")
    width, height = resolve_viewport(viewport_spec)
    device_scale = float(flow.get("device_scale", 2.0))
    is_mobile = isinstance(viewport_spec, str) and viewport_spec.lower() in ("mobile", "vertical")

    with ChromeSession(
        width=width,
        height=height,
        device_scale_factor=device_scale,
        mobile=is_mobile,
    ) as cdp:
        return execute_flow_on_cdp(cdp, flow, out_dir=out_dir, allow_remote=allow_remote)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run declarative Chrome CDP web navigation & hybrid live capture."
    )
    parser.add_argument("flow_file", type=Path, help="Path to flow.json.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for captures.")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly allow non-localhost URLs.",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    manifest = run_flow_file(args.flow_file, args.out_dir, allow_remote=args.allow_remote)
    manifest["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
