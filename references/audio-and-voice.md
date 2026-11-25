# DemoCraft Audio, SFX & Multi-Provider Voiceover Reference (`v1.3.2`)

DemoCraft composes sound in **three clean, zero-bloat layers**: **Music Bed** + **Timed SFX** + **Voiceover** (or mute-friendly **Caption Bar**).

## 1. Multi-Mood Music Beds (`scripts/music_bed.py` + BYO)
Choose a built-in royalty-free procedural mood OR pass any user-supplied track (`--music my-track.mp3`):

| Mood | BPM | Character | Best For |
| :--- | :---: | :--- | :--- |
| `ambient-calm` | `80` | Warm stereo pads, subtle sub breath, gentle shimmer | Calm `tutorial` walkthroughs & explainers |
| `harmonic-simple` | `96` | Electric-piano-like chords, soft warm pulse | Polished SaaS, B2B product demos |
| `modern-clean` | `114` | Punchy kick, crisp hats, syncopated plucked chords | Social commercials, feature spotlights |
| `tech-spectacular` | `124` | Energetic electro drive, pulsing 16th bass, bright pads | Flagship launches, high-energy reveals |

```bash
python3 <skill-dir>/scripts/music_bed.py modern-clean \
  --duration 30 --output <output-dir>/work/music.wav \
  --beats-out <output-dir>/work/music.beats.json
```

For BYO tracks (`--music path/to/track.mp3`), extract BPM and `strongCues` on demand (zero global pip installs):
```bash
python3 <skill-dir>/scripts/analyze_beats.py path/to/track.mp3 -o <output-dir>/work/music.beats.json
```

## 2. Curated 100% CC0 SFX + Procedural DSP SFX (`scripts/sfx_synth.py`)
All bundled SFX under `assets/audio/sfx/` are **CC0 1.0 Public Domain** (zero attribution required):
- **`ui/`**: `click_001.ogg`, `click_003.ogg`, `drop_001.ogg`, `drop_002.ogg`, `switch_001.ogg`, `switch_004.ogg`, `select_008.ogg`, `bong_001.ogg`
- **`impacts/`**: `impactSoft_medium_000.ogg`, `impactSoft_medium_001.ogg`, `impactBell_heavy_000.ogg`, `impactGlass_light_001.ogg`
- **`typing/`**: `keypress-001.wav` – `keypress-008.wav` (randomize per keystroke)
- **Procedural (`sfx_synth.py` or inline `synth:<preset>[:dur]` inside `sfx_cues.json`):** `whoosh`, `riser`, `laser_tech`, `pop`, `click`, `sub_drop`, `success_chime` — using `"sfx": "synth:whoosh:0.38"` in `sfx_cues.json` synthesizes ephemerally in `/tmp` with zero duplicate `.wav` files in `work/`.

```bash
python3 <skill-dir>/scripts/sfx_synth.py whoosh --duration 0.35 -o <output-dir>/work/whoosh.wav
```

**Mixing Discipline:** Less is more—use `3–8` subtle SFX cues (`0.0–0.08s` before visual impact). When voiceover is active, keep SFX subdued (`0.22–0.40` or pass `--sfx-scale 0.45`) so chimes, flashes, and transitions never compete with the narrator.

## 3. Pluggable Multi-Provider VoiceRouter (`scripts/voice_router.py`)

| Priority (`auto`) | Provider | Env Variable | Default Model / Runtime | Notes |
| :---: | :--- | :--- | :--- | :--- |
| `1` | **`byo`** | `--voice-file <path>` | User audio file | Measures duration automatically for *audio-first timing*. |
| `2` | **`gemini`** | `GEMINI_API_KEY` | `gemini-3.8-flash-tts` (`uv` ephemeral) | Studio-grade ES/EN commercial & tutorial prosody via `speech_metadata`. |
| `3` | **`openai`** | `OPENAI_API_KEY` | `gpt-4o-mini-tts` (**pure Python stdlib REST**) | Supports expressive tone `instructions`; zero extra SDKs or `uv` needed. |
| `4` | **`elevenlabs`** | `ELEVENLABS_API_KEY` | `eleven_multilingual_v2` (**pure Python stdlib REST**) | Studio / custom cloned voices (optional `ELEVENLABS_VOICE_ID`); zero extra SDKs. |
| `5` | **`kokoro`** | *(none — `$0` offline)* | `kokoro-onnx` FP16 (`uv` ephemeral) | Automatic offline fallback when no cloud key is set or `--offline` is passed. |
| `—` | **`none`** | *(none)* | Mute / captions-only | Clean Caption Bar + `.srt` sidecars without voiceover. |

*(Note: Anthropic / Claude does not offer a native TTS audio generation API.)*

### Safe API Key Setup Protocol (NEVER Paste Keys in Chat)
When a user selects a cloud provider (`gemini`, `openai`, or `elevenlabs`) and `probe.py --json` reports its key as `false`:
1. **Explicitly advise the user NOT to paste their API key into the chat.**
2. Instruct them to put **only** the provider key they chose into a local **gitignored** `.env` or `.env.local` file (copying `assets/templates/democraft.env.example`) and lock permissions with `chmod 600`:
   ```dotenv
   # Example: save inside a gitignored .env or .env.local (never commit to Git)
   # Uncomment ONLY the provider you want to use:

   GEMINI_API_KEY=AIzaSy_YOUR_KEY_HERE
   # OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE
   # ELEVENLABS_API_KEY=sk_YOUR_KEY_HERE
   # ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
   ```
   *(Alternatively, they can export the variable in their terminal shell: `export OPENAI_API_KEY="sk-proj-..."`.)*
3. Pass the path directly via `--env-file` so `voice_router.py` loads the key strictly in process memory — **the AI agent must never read, display, or log the `.env` file**:
   ```bash
   # Auto-cascade or explicit provider (gemini | openai | elevenlabs | kokoro | none)
   python3 <skill-dir>/scripts/voice_router.py \
     --from-file <output-dir>/work/storyboard.json --lang es --mode promo \
     --provider auto --env-file /path/to/.env.local \
     --output <output-dir>/work/voice.wav
   ```

**Audio-First Timing Rule:** Generate voiceover *before* locking final scene durations. Check `audio_duration_seconds` and align scene cuts cleanly to the spoken narration (staying within the mode's soft cap + grace margin).

## 4. Three-Layer Mixing & Auto-Ducking (`scripts/audio_mixer.py`)
Automatically ducks background music (`0.38` → `0.19`) via FFmpeg `sidechaincompress` whenever voiceover speaks, synthesizes `--music-mood` and `synth:<preset>[:dur]` SFX cues ephemerally in `/tmp` (zero duplicate `.wav` clutter in `work/`), applies smooth fade-in/out, and outputs `mix.wav` ready for `encode_video.py --audio --clean-work keep-editable`:

```bash
python3 <skill-dir>/scripts/audio_mixer.py \
  --music-mood modern-clean \
  --voice <output-dir>/work/voice.wav \
  --sfx-cues <output-dir>/work/sfx_cues.json \
  --music-volume 0.38 --duck-volume 0.19 --sfx-scale 0.45 \
  --duration 30 --output <output-dir>/work/mix.wav
```
*(Pass `--music path/to/custom.mp3` instead of `--music-mood` for BYO tracks.)*
