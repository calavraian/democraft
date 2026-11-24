# DemoCraft (`v1.2`)

**Platform-agnostic, zero-bloat promo & demo video creator** built on the open `SKILL.md` specification (works with Antigravity, Claude Code, Codex, OpenCode, and Cursor).

## Why DemoCraft?
- **Zero `npx` / Zero global bloat:** Core scripts run on Python 3.10+ stdlib; optional TTS/beat analysis and FFmpeg execute ephemerally via `uv` (or system binaries).
- **Full 3-layer sound (`v1.2`):** Royalty-free multi-mood music beds (`ambient-calm`, `harmonic-simple`, `modern-clean`, `tech-spectacular`) + curated **100% CC0** SFX & procedural DSP effects + BYO audio + pluggable `VoiceRouter` (`gemini-3.8-flash-tts` → `kokoro-onnx` offline fallback) with FFmpeg auto-ducking.
- **Hybrid live web capture (`v1.1`):** Declaratively navigate a live local web app via Chrome CDP (`capture_flow.py`) to capture Retina step screens + automatic normalized button highlight coordinates (`captures.json`) + scene-palette highlight recycling + smooth `record_scroll` frame sequences.
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
- **v1.0 (Completed):** Core visual engine (HTML/CSS 3D + wireframe mesh), minimal `storyboard.json`, Caption Bar + `.srt`, Chrome CDP stdlib capture, zero-bloat FFmpeg + Frame-0 bake.
- **v1.1 (Completed):** Shared `cdp_client.py` + declarative live web app navigation & hybrid capture (`capture_flow.py`: Retina stills + normalized highlight boxes + scene-palette recycling + smooth `record_scroll`).
- **v1.2 (Current):** Multi-mood royalty-free music beds, curated 100% CC0 + procedural SFX, BYO beat sync, `VoiceRouter` (`gemini-3.8-flash-tts` → `kokoro-onnx` fallback), and 3-layer FFmpeg auto-ducking mixer.
- **v2.0:** Optional decoupled Blender 3D / real wireframe EEVEE add-on.
