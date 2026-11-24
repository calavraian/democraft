# Deterministic HTML Composition Contract

Every DemoCraft HTML composition MUST be a **pure deterministic function of time `t` (in seconds)** so `render_frames.py` can seek to any exact timestamp without clock drift, CSS animation jitter, or dropped frames.

## 1. Required Global Hooks
```js
/**
 * Renders the exact visual state for timestamp `t` (float seconds, >= 0).
 * Must update all scenes, CSS 3D transforms, Canvas/WebGL meshes, and Caption Bar synchronously.
 * May return `true` or a Promise resolving once painting is ready.
 */
window.__DEMOCRAFT_SEEK__ = function (t) { /* ... */ return true; };

/**
 * Optional: accepts an array of `{start: number, end: number, text: string}` cues
 * injected by `render_frames.py --captions <file> --lang <code>`.
 */
window.__DEMOCRAFT_SET_CAPTIONS__ = function (cues) { /* ... */ };

/**
 * Optional: toggles visual safe-zone guide overlays (for pre-render QA stills).
 */
window.__DEMOCRAFT_TOGGLE_SAFE_ZONES__ = function (enabled) { /* ... */ };
```

## 2. Rules for Zero-Drift Deterministic Rendering
1. **No CSS `@keyframes` or `transition` for timeline motion:** Browser wall-clock CSS animations drift out of sync during headless frame capture. Compute normalized scene progress `p = clamp((t - start) / dur, 0, 1)`, apply an easing function (`easeOutCubic`, `easeOutBack`, `easeInOutQuart`), and set inline `style.transform`, `style.opacity`, and `style.display` inside `__DEMOCRAFT_SEEK__(t)`.
2. **Explicit Scene Visibility:** Inactive scenes MUST use `display: none` (never `visibility: hidden`).
3. **Relative Assets Only:** Serve all logos, fonts, and screenshots from the composition folder (`assets/...`). `render_frames.py` mounts the HTML's parent directory on a local `127.0.0.1` loopback HTTP server. Never reference external hotlinks or `/Users/...` absolute paths.
4. **Exact Viewport Dimensions:** Set `html, body { margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; }` and design responsively for `1080x1920` (`vertical`), `1920x1080` (`landscape`), or `1080x1080` (`square`).
5. **Pseudo-3D & Wireframe-Mesh Aesthetics (Zero Blender Required):**
   - Use CSS 3D containers (`perspective: 1400px; transform-style: preserve-3d;`) with gentle `rotateX`, `rotateY`, `translateZ`, and layered elevation shadows for UI cards and device frames.
   - Use a deterministic `<canvas>` 3D perspective wireframe-mesh layer (projected 3D grid wave / tactical pitch lines / floating geometric wireframe) drawn directly inside `__DEMOCRAFT_SEEK__(t)` for modern depth.
