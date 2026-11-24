# Declarative Live Web App Capture (`capture_flow.py`)

Use `scripts/capture_flow.py` to capture **authentic, live web app screens and smooth real scroll sequences** over Chrome DevTools Protocol — with **zero Playwright, zero `npx`, and zero global installs**.

## Hybrid Strategy (Promo vs. Tutorial)
- **Promo / Social clips:** Use crisp Retina step screenshots (`capture`) with normalized `highlight_selector` / `highlight_text` bounding boxes (`captures.json`), then animate 3D tilt, zooms, cursor glides, and transitions in HTML/CSS.
- **Feature Demos / Tutorials:** Combine Retina step captures **plus** `record_scroll` sequences (`frame_00000.png`...) so viewers see authentic scrolling and layout depth inside the real app, interleaved with `freeze_s` pauses and animated highlight boxes derived directly from `captures.json`.

## Supported `flow.json` Actions
| Action | Fields | Purpose |
| :--- | :--- | :--- |
| `goto` | `path` (joined to `base_url`) or `url`, optional `wait_s` | Navigate to route and wait for `load` + `document.fonts.ready`. |
| `wait_for` | `selector` or `text`, optional `timeout_s` (default `10`) | Wait until element exists with non-zero visible bounding box (SPA-safe). |
| `click` | `selector`, optional `record_cue: true`, `wait_s` | Real CDP mouse move + press + release on element center. |
| `click_text` | `text`, optional `record_cue: true`, `wait_s` | Click visible button/link/tab matching substring text. |
| `type` | `selector`, **`value_env`** *(preferred for credentials)* or `value` | Focus input and inject text via CDP `Input.insertText` (React-safe). |
| `scroll` | `y` or `to_bottom: true`, optional `selector` (container) | Scroll window or inner scroll container. |
| `pause` | `seconds` | Short settle pause (e.g. after toast/modal transitions). |
| `capture` | `name`, optional `highlight_selector` / `highlight_text` | Save Retina PNG + normalized `[x, y, w, h]` & center `[cx, cy]` to `captures.json`. |
| `record_scroll` | `name`, `from_y`, `to_y` or `to_bottom: true`, `duration_s`, `fps`, optional `selector` | Smooth `easeInOutCubic` real-scroll capture into `<name>/frame_%05d.png`. |

## Security Rules
1. **Localhost-first:** Non-loopback URLs are blocked by default; pass `--allow-remote` explicitly only for trusted sites.
2. **Never hardcode passwords or tokens in `flow.json`:** Always use `"value_env": "MY_DEMO_PASS"` so credentials stay in environment variables and never touch disk or `captures.json`.
3. **Ephemeral profile:** Each run launches a fresh temporary Chrome profile that is deleted automatically on exit.

## Example Invocation
```bash
python3 <skill-dir>/scripts/capture_flow.py <output-dir>/work/flow.json \
  --out-dir <output-dir>/work/composition/assets/captures
```

## Using `captures.json` & `record_scroll` Inside a Composition
- Display static captures as `<img src="assets/captures/01_dashboard.png">` inside CSS 3D device frames, and overlay a highlight ring positioned directly via `highlight.bounds_norm` (`left: x*100%`, `top: y*100%`, `width: w*100%`, `height: h*100%`).
- **Coherent Highlight Styling (Zero Rainbow, Guaranteed Contrast):**
  - `capture_flow.py` harvests the app's own native colors (`highlight_theme.scene_palette`) and selects **one single native scene color** (`highlight_theme.recommended_hex`) that maximizes worst-case contrast across every clicked/highlighted button in the flow (so it never blends into a same-color CTA button and never changes color step to step).
  - Always give the highlight box **generous breathing room (`+8px` / `~0.6–1.0%` offset)**, a **crisp white/cream inner separator ring** (`box-shadow: inset 0 0 0 3px #FFFFFF`), the single recycled `recommended_hex` outer ring, and a **subtle Spotlight Scrim** (`box-shadow: 0 0 0 9999px rgba(24, 24, 27, 0.26)`) so the target pops cleanly on any background.
- Play `record_scroll` sequences deterministically inside `window.__DEMOCRAFT_SEEK__(t)` by mapping local scene time `lt` to `frameIdx = Math.min(frames - 1, Math.floor(lt * fps))` and swapping `<img src="assets/captures/02_scroll/frame_00012.png">` (preloaded on boot — zero `<video>` codec drift).
