# DemoCraft (`v1.3`)

**Platform-agnostic, zero-bloat promo, commercial & feature-tutorial video creator for software products.**

Built on the open `SKILL.md` specification — works natively across **Google Antigravity, Claude Code, OpenAI Codex, OpenCode, and Cursor** with **zero `npx`, zero `node_modules`, and zero global package installs**.

---

## Why DemoCraft?
- **Zero Bloat, Maximum Portability:** Core scripts use Python 3.10+ stdlib only (~720 KB total including audio assets). Uses the Chromium browser you already have (`Chrome`, `Brave`, `Edge`, or `Chromium`) via pure-stdlib CDP, and encodes MP4 via system `ffmpeg`, ephemeral `uv run --with imageio-ffmpeg`, or `docker`.
- **Two Editorial Modes:**
  - **`promo`** (`15–35s` target, `45s` soft cap + `5s` grace): crisp commercial teasers & feature spotlights.
  - **`tutorial`** (`45–120s` target, `150s` soft cap + `10s` grace): calm step-by-step walkthroughs with optional `freeze_s` pauses.
- **Hybrid Live Web App Capture (`capture_flow.py`):** Declaratively navigate local web apps via `flow.json` to capture Retina step screenshots, normalized highlight coordinates (`captures.json`), scene-palette highlight recycling (zero green-on-green clashes), smooth `record_scroll`, and selective live `record_drag` sequences (for tactical boards, Kanban, canvas editors, sliders).
- **3-Layer Broadcast Audio & Multi-Provider VoiceRouter:**
  - **Music Beds:** 4 royalty-free procedural moods (`ambient-calm`, `harmonic-simple`, `modern-clean`, `tech-spectacular`) with beat grids + BYO track beat analyzer (`analyze_beats.py`).
  - **SFX:** Curated **100% CC0 Public Domain** UI/impact/typing library (zero attribution required) + procedural DSP synth (`sfx_synth.py`).
  - **Pluggable Voiceover (`voice_router.py`):** **Gemini 3.8 TTS**, **OpenAI TTS (`gpt-4o-mini-tts`)**, **ElevenLabs (`eleven_multilingual_v2`)**, offline **`$0` Kokoro ONNX**, **BYO narration**, or **mute captions-only** — with automatic FFmpeg `sidechaincompress` music ducking under voice.
- **5 Selectable Deterministic 3D Canvas Backgrounds (`backgrounds.js`):** `wireframe-wave`, `floating-polyhedra`, `orbital-rings`, `depth-grid-particles`, `soft-aurora-mesh`, or `none`.
- **Social-Ready Deliverables:** `landscape` (`1920×1080`), `vertical` (`1080×1920` Reels/TikTok/Shorts with safe-zone QA), or `square` (`1080×1080`), baked **Frame-0 poster (`poster.jpg`)**, multi-language **Caption Bar + `.srt`**, and grounded **`share-copy.txt`**.

---

## Prerequisites
- **Python 3.10+** (standard library only for core workflow)
- **Chromium-based browser** already installed (`Google Chrome`, `Brave`, `Edge`, or `Chromium`)
- **One FFmpeg runner:** `ffmpeg` on `PATH`, [`uv`](https://docs.astral.sh/uv/) *(recommended — zero global installs)*, or `docker`

Verify your environment without installing anything:
```bash
python3 scripts/probe.py
```

---

## Installation (Pick Your AI Coding Agent)

Clone the skill into your preferred agent's skills directory (or symlink it):

```bash
# Google Antigravity
git clone <repo-url> ~/.gemini/config/skills/democraft

# Claude Code
git clone <repo-url> ~/.claude/skills/democraft

# OpenAI Codex
git clone <repo-url> ~/.codex/skills/democraft

# Cursor / OpenCode (project-local or user skills folder)
git clone <repo-url> .agents/skills/democraft
```

Then ask your agent naturally (or invoke `/democraft`):
> *"Create a 30-second commercial promo for my app running at localhost:3000 highlighting the tactical board."*

DemoCraft will automatically probe your machine, run a brief preflight interview (format, voice preference, visual style, output folder), and guide you safely through every step.

---

## Optional Voiceover Providers & Safe API Key Setup

You **do not need any API key** to use DemoCraft (captions-only, BYO audio, and offline `Kokoro` TTS all work for `$0`).

If you want expressive cloud voiceover, DemoCraft supports:

| Provider | Env Variable | Model | Implementation |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | `GEMINI_API_KEY` | `gemini-3.8-flash-tts` | Ephemeral `uv` (`google-genai>=3.0.0`) |
| **OpenAI** | `OPENAI_API_KEY` | `gpt-4o-mini-tts` | Pure Python stdlib REST (zero deps) |
| **ElevenLabs** | `ELEVENLABS_API_KEY` *(+ optional `ELEVENLABS_VOICE_ID`)* | `eleven_multilingual_v2` | Pure Python stdlib REST (zero deps) |
| **Kokoro (Offline)** | *(none — `$0`)* | `kokoro-onnx` FP16 | Ephemeral `uv` fallback |

### Safe Key Handling (Never Paste Keys in Chat)
Copy `assets/templates/democraft.env.example` into a **gitignored** `.env.local` file (`chmod 600 .env.local`) and uncomment **only** the provider you want:

```dotenv
# Save in a gitignored .env.local (never commit, never paste in chat)
GEMINI_API_KEY=AIzaSy_YOUR_KEY_HERE
# OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
# ELEVENLABS_API_KEY=sk_YOUR_KEY_HERE
# ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
```

Then pass `--env-file /path/to/.env.local` to `probe.py` and `voice_router.py` — keys are loaded strictly in memory and never logged or read into chat context.

---

## Running Unit Tests
```bash
pytest tests -v
```

## License
- Code, scripts, templates, and documentation: **MIT License** ([LICENSE](./LICENSE))
- Bundled sound effects (`assets/audio/sfx/`): **CC0 1.0 Public Domain** ([assets/audio/LICENSE-CC0.md](./assets/audio/LICENSE-CC0.md))
