# Declarative Live Web App Capture (`capture_flow.py`)

Use `scripts/capture_flow.py` to capture **authentic, live web app screens, smooth real scroll sequences, and selective drag-and-drop interactions** over Chrome DevTools Protocol — with **zero Playwright, zero `npx`, and zero global installs**.

## Hybrid Strategy (Choose the Right Capture Type — Don't Overuse Recordings!)
- **Standard Promo / Social Clips (Default):** Use crisp Retina step screenshots (`capture`) with normalized `highlight_selector` / `highlight_text` bounding boxes (`captures.json`), then animate 3D tilt, zooms, cursor glides, and clean transitions in HTML/CSS.
- **Feature Demos / Tutorials:** Combine Retina step captures **plus** `record_scroll` ONLY where scrolling reveals meaningful layout depth (feeds, long dashboards, tables), interleaved with `freeze_s` pauses.
- **Selective `record_drag` Policy (Use Intelligently, NOT Everywhere):** Use `record_drag` **ONLY** when physical drag-and-drop is the actual hero capability being showcased (e.g., a sports tactical board, Kanban board, node/canvas editor, calendar drag, or range slider). Never use `record_drag` for routine button clicks, tabs, or form flows where crisp stills + CSS motion are lighter, sharper, and easier to time.

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
| `record_drag` | `name`, source (`selector`/`text`/`from_norm`), target (`to_selector`/`to_text`/`to_norm` or `dx`/`dy`), optional `arc_dy`, `duration_s`, `fps` | **Selective use only:** real CDP pointer drag (`mousePressed → eased bezier mouseMoved → mouseReleased`) recording `<name>/frame_%05d.png` + per-frame normalized `pointer_frames` in `captures.json`. |

## Security Rules
1. **Localhost-first:** Non-loopback URLs are blocked by default; pass `--allow-remote` explicitly only for trusted sites.
2. **Never hardcode passwords or tokens in `flow.json`:** Always use `"value_env": "MY_DEMO_PASS"` so credentials stay in environment variables and never touch disk or `captures.json`.
3. **Ephemeral profile:** Each run launches a fresh temporary Chrome profile that is deleted automatically on exit.

## Example Invocation
```bash
python3 <skill-dir>/scripts/capture_flow.py <output-dir>/work/flow.json \
  --out-dir <output-dir>/work/composition/assets/captures
```

## Using `captures.json`, `record_scroll` & `record_drag` Inside a Composition
- Display static captures as `<img src="assets/captures/01_dashboard.png">` (or blit preloaded images onto a `<canvas>`) inside CSS 3D device frames, and overlay a highlight ring positioned directly via `highlight.bounds_norm` (`left: x*100%`, `top: y*100%`, `width: w*100%`, `height: h*100%`).
- **Coherent Highlight Styling (Zero Rainbow, Guaranteed Contrast):**
  - `capture_flow.py` harvests the app's own native colors (`highlight_theme.scene_palette`) and selects **one single native scene color** (`highlight_theme.recommended_hex`) that maximizes worst-case contrast across every clicked/highlighted button in the flow.
  - Always give the highlight box **generous breathing room (`+8px`)**, a **crisp white inner separator ring** (`box-shadow: inset 0 0 0 3px #FFFFFF`), the single recycled `recommended_hex` outer ring, and a **subtle Spotlight Scrim** (`box-shadow: 0 0 0 9999px rgba(24, 24, 27, 0.24)`) that fades out once the click completes.
- Play `record_scroll` and `record_drag` sequences deterministically inside `window.__DEMOCRAFT_SEEK__(t)` by mapping local scene time `lt` to `frameIdx = Math.min(frames - 1, Math.floor(lt * fps))` and reading `pointer_frames[frameIdx]` (`cx`, `cy`) to sync a non-blocking cursor and dashed trajectory overlay.
