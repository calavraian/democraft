#!/usr/bin/env python3
"""DemoCraft capability probe (Python stdlib only — zero external dependencies).

Detects available local browsers, FFmpeg execution strategies, and optional
modules (Blender, Gemini API key presence) without installing or modifying
anything on the host machine.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

MACOS_BROWSER_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

LINUX_BROWSER_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "microsoft-edge",
)

MACOS_BLENDER_CANDIDATES = (
    "/Applications/Blender.app/Contents/MacOS/Blender",
)


def find_chromium_browser() -> str | None:
    """Locates an installed Chromium-based browser executable on the host."""
    env_override = os.getenv("DEMOCRAFT_BROWSER")
    if env_override and Path(env_override).is_file():
        return env_override

    if sys.platform == "darwin":
        for candidate in MACOS_BROWSER_CANDIDATES:
            if Path(candidate).is_file():
                return candidate

    for binary in LINUX_BROWSER_BINARIES:
        found = shutil.which(binary)
        if found:
            return found

    return None


def find_blender() -> str | None:
    """Locates an optional Blender executable for future v2.0 3D hero shots."""
    found = shutil.which("blender")
    if found:
        return found
    if sys.platform == "darwin":
        for candidate in MACOS_BLENDER_CANDIDATES:
            if Path(candidate).is_file():
                return candidate
    return None


def resolve_ffmpeg_strategy() -> str:
    """Determines the best zero-bloat FFmpeg execution strategy available."""
    if shutil.which("ffmpeg"):
        return "system"
    if shutil.which("uv"):
        return "uv"
    if shutil.which("docker"):
        return "docker"
    return "none"


def probe_environment() -> dict[str, Any]:
    """Returns a structured capability report without exposing any secret values."""
    browser_path = find_chromium_browser()
    ffmpeg_strategy = resolve_ffmpeg_strategy()
    blender_path = find_blender()

    missing: list[str] = []
    if not browser_path:
        missing.append("chromium-browser (Google Chrome / Brave / Edge / Chromium)")
    if ffmpeg_strategy == "none":
        missing.append("ffmpeg-runner (ffmpeg, uv, or docker)")

    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "core_ready": len(missing) == 0,
        "browser_path": browser_path,
        "ffmpeg_strategy": ffmpeg_strategy,
        "missing_requirements": missing,
        "optional": {
            "uv_available": shutil.which("uv") is not None,
            "docker_available": shutil.which("docker") is not None,
            "blender_available": blender_path is not None,
            "blender_path": blender_path,
            "gemini_api_key_set": bool(os.getenv("GEMINI_API_KEY")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe local DemoCraft capabilities.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args()

    report = probe_environment()
    if args.json:
        print(json.dumps(report, indent=2))
        return

    status = "READY" if report["core_ready"] else "MISSING REQUIREMENTS"
    print(f"DemoCraft Probe: {status}")
    print(f"  OS / Python    : {report['os']} ({report['arch']}) / Python {report['python']}")
    print(f"  Browser (CDP)  : {report['browser_path'] or 'NOT FOUND'}")
    print(f"  FFmpeg runner  : {report['ffmpeg_strategy']}")
    print(f"  Blender (v2.0) : {'available' if report['optional']['blender_available'] else 'not installed (optional)'}")
    print(f"  Gemini API key : {'configured' if report['optional']['gemini_api_key_set'] else 'not set (optional)'}")
    if report["missing_requirements"]:
        print("  Missing        : " + ", ".join(report["missing_requirements"]))


if __name__ == "__main__":
    main()
