# DemoCraft (`v1.3.2`)

**Platform-agnostic, zero-bloat promo, commercial & feature-tutorial video creator for software products.**

Built on the open `SKILL.md` specification — works natively across **Google Antigravity, Claude Code, OpenAI Codex, OpenCode, and Cursor** with **zero `npx`, zero `node_modules`, and zero global package installs**.

---

## Why DemoCraft?
- **Zero Bloat, Clean Disk Footprint:** Core scripts run on Python 3.10+ stdlib (~720 KB total including audio assets). Uses your existing Chromium browser (`Chrome`, `Brave`, `Edge`, or `Chromium`), encodes via `ffmpeg` / `uv` / `docker`, and automatically cleans up heavy temporary frames and derived audio after encoding so projects never pile up gigabytes of clutter.
- **Two Editorial Modes:**
  - **`promo`** (`15–35s` target, `45s` soft cap + `5s` grace): crisp commercial teasers & feature spotlights.
  - **`tutorial`** (`45–120s` target, `150s` soft cap + `10s` grace): calm step-by-step walkthroughs with optional `freeze_s` pauses.
- **Hybrid Live Web App Capture:** Navigates local web apps declaratively (`flow.json`) for Retina step screens, scene-matched highlights (zero color clashes), smooth real scroll captures, and selective live drag-and-drop recordings (tactical boards, Kanban, canvas editors, sliders).
- **3-Layer Audio & Multi-Provider Voiceover:**
  - **Music Beds:** 4 built-in royalty-free moods (`ambient-calm`, `harmonic-simple`, `modern-clean`, `tech-spectacular`) synthesized on demand without duplicating files, plus support for your own tracks (BYO).
  - **SFX:** Curated **100% CC0 Public Domain** UI/impact/typing library (zero attribution required) + on-the-fly synthesized effects.
  - **Pluggable Voiceover:** **Google Gemini**, **OpenAI**, **ElevenLabs** *(including free-tier automatic fallback)*, **`$0` offline Kokoro**, **BYO narration**, or **captions-only** — with automatic music ducking under speech.
- **5 Selectable 3D Canvas Backgrounds:** `wireframe-wave`, `floating-polyhedra`, `orbital-rings`, `depth-grid-particles`, `soft-aurora-mesh`, or `none`.
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

## Installation (Pick Your Preferred Method)

Modern `SKILL.md` agents (**Antigravity, Claude Code, Codex, Cursor, OpenCode**) automatically register any folder containing `SKILL.md` inside their skills directory — no manual config registry required.

### Option A: Install with Your AI Agent (1 Prompt — Zero Manual Commands)

Simply paste this prompt into **Antigravity, Claude Code, Codex, Cursor, or OpenCode**:

> *"Install the DemoCraft skill from `https://github.com/calavraian/democraft.git` following its README instructions, register it in my skills directory, and run `scripts/probe.py` to confirm my environment is ready."*

<details>
<summary><strong>Agent Installation Protocol (Machine-Readable Steps for AI Agents)</strong></summary>

1. Clone `https://github.com/calavraian/democraft.git` into a persistent local directory (or directly into your agent's skills directory).
2. Run the stdlib registrar (zero `npx`, zero pip installs):
   ```bash
   python3 scripts/install.py --agent auto
   ```
   *(Pass `--agent antigravity`, `--agent claude`, `--agent codex`, `--agent cursor`, `--agent all`, or `--project <repo>` as appropriate; add `--dry-run` first if you want to preview paths.)*
3. Verify local capabilities without installing global packages or reading secrets:
   ```bash
   python3 scripts/probe.py --json
   ```
4. Report registration path + readiness (`core_ready`, `browser_path`, `ffmpeg_strategy`, `available_voice_providers`). Never ask the user to paste API keys in chat — point them to `assets/templates/democraft.env.example` if they later want cloud TTS.

</details>

### Option B: One-Command CLI Installer (Auto-Detects All Your Agents)

Clone once and let `scripts/install.py` register DemoCraft across every installed agent (`--symlink` tracks `git pull`; use `--mode copy` for a standalone copy):

```bash
git clone https://github.com/calavraian/democraft.git ~/.local/share/democraft
python3 ~/.local/share/democraft/scripts/install.py --agent auto
```

Useful installer flags:
- `--dry-run` — preview target directories without touching disk
- `--agent antigravity|claude|codex|cursor|all` — target specific agent(s)
- `--project /path/to/repo` — install project-locally in `.agents/skills/democraft`
- `--uninstall` — cleanly unregister without deleting the cloned repo

### Option C: Direct `git clone` per Agent

```bash
# Google Antigravity
git clone https://github.com/calavraian/democraft.git ~/.gemini/config/skills/democraft

# Claude Code
git clone https://github.com/calavraian/democraft.git ~/.claude/skills/democraft

# OpenAI Codex
git clone https://github.com/calavraian/democraft.git ~/.codex/skills/democraft

# Cursor / OpenCode (user-level or project-local .agents/skills/democraft)
git clone https://github.com/calavraian/democraft.git ~/.agents/skills/democraft
```

Then ask your agent naturally (or invoke `/democraft`):
> *"Create a 30-second commercial promo for my app running at localhost:3000 highlighting the tactical board."*

DemoCraft will automatically probe your machine, run a brief preflight interview (format, voice preference, visual style, output folder), and guide you safely through every step.

---

## Optional Voiceover Providers & Safe API Key Setup

You **do not need any API key** to use DemoCraft (captions-only, BYO audio, and offline `Kokoro` TTS all work for `$0`).

If you want expressive cloud voiceover, DemoCraft supports:

| Provider | Env Variable | Notes |
| :--- | :--- | :--- |
| **Google Gemini** | `GEMINI_API_KEY` | Expressive commercial & tutorial styles in ES/EN (`gemini-3.8-flash-tts`) |
| **OpenAI** | `OPENAI_API_KEY` | Expressive tone directives (`gpt-4o-mini-tts`), zero extra installs |
| **ElevenLabs** | `ELEVENLABS_API_KEY` *(+ optional `ELEVENLABS_VOICE_ID`)* | Studio & custom voices (`eleven_multilingual_v2`); auto-falls back to a free-tier premade voice if a library voice requires a paid plan |
| **Kokoro (Offline)** | *(none — `$0`)* | Automatic local offline fallback (`kokoro-onnx`) |
| **BYO / Mute** | *(none — `$0`)* | Bring your own audio (`--voice-file`) or render captions-only |

*(Note: Anthropic / Claude does not provide a native voice TTS API; Claude Code users can pair DemoCraft with Gemini, OpenAI, ElevenLabs, free offline Kokoro, or BYO audio.)*

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
