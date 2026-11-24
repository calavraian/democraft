# DemoCraft Audio, SFX & Voiceover Reference (`v1.2`)

DemoCraft composes sound in **three clean, zero-bloat layers**: **Music Bed** + **Timed SFX** + **Voiceover** (or mute-friendly **Caption Bar**).

## 1. Multi-Mood Music Beds (`scripts/music_bed.py` + BYO)
Choose a built-in royalty-free procedural mood OR pass any user-supplied track (`--music my-track.mp3`):

| Mood | BPM | Character | Best For |
| :--- | :---: | :--- | :--- |
| `ambient-calm` | `80` | Warm stereo pads, subtle sub breath, gentle shimmer | Calm `tutorial` walkthroughs & explainers |
| `harmonic-simple` | `96` | Electric-piano-like chords, soft warm pulse | Polished SaaS, B2B product demos |
| `modern-clean` | `114` | Punchy kick, crisp hats, syncopated plucked chords | Social commercials, GoalPad feature promos |
| `tech-spectacular` | `124` | Energetic electro drive, pulsing 16th bass, bright pads | Flagship launches, high-energy tech reveals |

```bash
python3 <skill-dir>/scripts/music_bed.py modern-clean \
  --duration 20 --output <output-dir>/work/music.wav \
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
- **Procedural (`sfx_synth.py`, exact duration):** `whoosh`, `riser`, `laser_tech`, `pop`, `click`, `sub_drop`, `success_chime`

```bash
python3 <skill-dir>/scripts/sfx_synth.py whoosh --duration 0.35 -o <output-dir>/work/whoosh.wav
```

**Mixing Discipline:** Less is more—use `3–6` subtle SFX cues (`0.0–0.08s` before visual impact). When voiceover is active, keep SFX subdued (`0.22–0.40` or pass `--sfx-scale 0.55`) so chimes, flashes, and transitions never compete with the narrator.

## 3. Pluggable VoiceRouter Cascade (`scripts/voice_router.py`)
1. `--provider none`: captions-only (no voice track).
2. `--voice-file <path>`: BYO narration (measures duration automatically for *audio-first timing*).
3. `GEMINI_API_KEY` set (`--provider auto` or `gemini`): **`gemini-3.8-flash-tts`** via `v1beta` `interactions.create` + structured `speech_metadata` (studio-grade ES/EN commercial & tutorial prosody, 0 MB local models).
4. Offline fallback (no API key or `--offline`): **`kokoro-onnx`** via ephemeral `uv` (offline, `$0`).

```bash
python3 <skill-dir>/scripts/voice_router.py \
  --from-file <output-dir>/work/storyboard.json --lang es --mode promo \
  --output <output-dir>/work/voice.wav
```

**Audio-First Timing Rule:** Generate voiceover *before* locking final scene durations. Check `audio_duration_seconds` and align scene cuts cleanly to the spoken narration (staying within the mode's soft cap + grace margin).

## 4. Three-Layer Mixing & Auto-Ducking (`scripts/audio_mixer.py`)
Automatically ducks background music (`0.38` → `0.19`) via FFmpeg `sidechaincompress` whenever voiceover speaks, mixes subtle timed SFX cues (`--sfx-scale 0.55` when voice is active), applies smooth fade-in/out, and outputs a broadcast-clean `mix.wav` ready for `encode_video.py --audio`:

```bash
python3 <skill-dir>/scripts/audio_mixer.py \
  --music <output-dir>/work/music.wav \
  --voice <output-dir>/work/voice.wav \
  --sfx-cues <output-dir>/work/sfx_cues.json \
  --music-volume 0.38 --duck-volume 0.19 --sfx-scale 0.55 \
  --duration 21 --output <output-dir>/work/mix.wav
```
