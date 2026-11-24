# DemoCraft (`v1.0`)

**Platform-agnostic, zero-bloat promo & demo video creator** built on the open `SKILL.md` specification (works with Antigravity, Claude Code, Codex, OpenCode, and Cursor).

## Why DemoCraft?
- **Zero `npx` / Zero global bloat:** All v1.0 scripts (`probe.py`, `storyboard.py`, `captions.py`, `render_frames.py`, `encode_video.py`) run on **Python 3.10+ standard library only**.
- **Two built-in modes:** Fast **`promo`** teasers (`15–25s`, `+3s` grace) and calm **`tutorial`** feature walkthroughs (`45–150s`, `+10s` grace) driven by a minimal, non-rigid `storyboard.json` with optional `freeze_s` stops and wide creative latitude.
- **Uses tools you already have:** Captures frames deterministically using your existing Chrome/Brave/Edge/Chromium browser over local CDP, and encodes MP4 via system `ffmpeg`, ephemeral `uv run --with imageio-ffmpeg`, or `docker`.
- **Social-first & mute-ready:** Supports `vertical` (`1080x1920`), `landscape` (`1920x1080`), and `square` (`1080x1080`) with vertical Reels/TikTok/Shorts safe-zone verification, multi-language **Caption Bar** + `.srt` export, and **Frame-0 poster baking** so social thumbnails always show your strongest frame.
- **Modern 2D + Pseudo-3D depth:** HTML/CSS 3D perspective mockups + animated Canvas wireframe-mesh backgrounds — zero Blender required in v1.0.

## Quick Verification
```bash
# 1. Check detected local capabilities
python3 skills/democraft/scripts/probe.py --json

# 2. Run unit test suite
pytest skills/democraft/tests -v
```

## Roadmap
- **v1.0 (Current):** Core visual engine (HTML/CSS 3D + wireframe mesh), Caption Bar + `.srt`, Chrome CDP stdlib capture, zero-bloat FFmpeg + Frame-0 bake.
- **v1.1:** Declarative web app navigation scripts (`capture_flow.py`) over CDP.
- **v1.2:** Curated 100% CC0 multi-mood music & SFX + BYO beat sync + pluggable `VoiceRouter` (`gemini-3.8-flash-tts` → `kokoro-onnx` fallback).
- **v2.0:** Optional decoupled Blender 3D / real wireframe EEVEE add-on.
