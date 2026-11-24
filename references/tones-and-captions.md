# Tones, Moods & Multi-Language Caption Bar Guide

## 1. Commercial Tone Presets
| Tone | Visual Posture | Pacing & Motion | Best For |
| :--- | :--- | :--- | :--- |
| `polished` | Clean editorial, confident contrast, subtle CSS 3D tilt & gentle wireframe mesh | 4 scenes, calm holds (`3.5–5s`), soft cubic-bezier slides | B2B/SaaS, serious consumer apps (e.g. sports academies, fintech, productivity) |
| `launch` | Crisp startup reveal, bold typography, energetic card pop-ins | 4–5 scenes, snappy `0.35s` entrances, clean hard/slide cuts | Product Hunt, X/LinkedIn launches, new version announcements |
| `app-store` | Device-centric feature cards, bright legible highlights | 4–6 scenes, consistent slide rhythm, focused UI zooms | Mobile/responsive web previews, feature spotlights |
| `tutorial` | Calm guided walkthrough, step badge (`Step 1 of 3`), optional UI highlight & cursor cue | `45–150s` (`+10s` grace), deliberate `before_action` pauses, generous reading holds | Feature demos, onboarding guides, help-center clips |
| `cinematic` | Deep contrast, slower 3D perspective sweeps, prominent mesh glow | 3–4 scenes, dramatic holds, slow zoom-in | Flagship reveals, brand manifestos |
| `minimal` | High whitespace, restrained typography, micro-motion only | 3–4 scenes, clean fades, minimal chrome | Design tools, developer utilities |
| `playful` | Bouncy spring curves, lively badge pops, punchy copy | 5–6 scenes, upbeat tempo | Consumer social apps, creative tools |

## 2. Caption Bar Design (Mute-First & Multi-Language)
Because most social viewers watch muted, DemoCraft treats captions as a first-class visual layer:

- **Placement:**
  - `vertical` (`1080x1920`): bottom of the safe zone (`top: 1310px` to `1490px`, `left: 56px`, `right: 164px` — keeping clear of the right `140px` social action column and the bottom `384px` description bar).
  - `landscape` (`1920x1080`): centered lower-third (`bottom: 64px`, `max-width: 1360px`).
  - `square` (`1080x1080`): centered lower bar (`bottom: 58px`, `max-width: 920px`).
- **Styling:** High-contrast frosted/solid pill (`rgba(24, 24, 27, 0.88)` background, `#FBF9F2` or `#FFFFFF` crisp text, subtle brand accent left border or highlight keyword, `1.35` line-height, max 2 lines per cue).
- **Synchronization Rules:**
  - Keep each cue between `1.4s` and `4.5s` (`~6–14 words` max per cue).
  - Leave at least `0.08s` breath between consecutive cues so the viewer's eye registers the text refresh.
  - Author `captions.json` with language keys (`"es"`, `"en"`, etc.) so re-rendering a second language requires **zero changes to scene visuals**.

### Minimal Flexible `storyboard.json` Schema (Recommended Single Source of Truth)
Keep scenes intentionally minimal so the AI retains wide creative freedom over motion, 3D tilt, and layout. Only `id`, `duration_s`, and `intent`/`captions` are needed; `freeze_s`, `freeze_mode` (`before_action` | `after_action` | `hold`), and `cue` (`highlight`/`tap`) are completely optional (primarily for `tutorial` walkthroughs):

```json
{
  "name": "goalpad-attendance-guide",
  "mode": "tutorial",
  "format": "landscape",
  "tone": "tutorial",
  "default_lang": "es",
  "scenes": [
    {
      "id": "step_01_open_attendance",
      "duration_s": 8.0,
      "freeze_s": 2.5,
      "freeze_mode": "before_action",
      "intent": "Mostrar el panel principal y destacar Asistencia en el menú.",
      "captions": {
        "es": "Abre el módulo de Asistencia desde el menú lateral.",
        "en": "Open the Attendance module from the sidebar."
      },
      "cue": {
        "highlight": { "selector": "#nav-attendance" },
        "tap": { "at_s": 4.2 }
      }
    }
  ]
}
```
*(You can pass `storyboard.json` directly to `render_frames.py --captions` — `captions.py` also still accepts standalone `captions.json` files when preferred.)*
