/**
 * DemoCraft Deterministic 3D & Mesh Canvas Backgrounds (Zero external dependencies)
 *
 * Usage inside window.__DEMOCRAFT_SEEK__(t):
 *   DemoCraftBg.draw(ctx, width, height, t, "floating-polyhedra", { accent: "#059669" });
 *
 * Available styles:
 *   - "wireframe-wave"       : 3D perspective undulating wireframe surface
 *   - "floating-polyhedra"   : 3D wireframe cubes & octahedra rotating in depth
 *   - "orbital-rings"        : Tilted 3D concentric rings with orbiting light nodes
 *   - "depth-grid-particles" : 3D parallax particle constellation with soft links
 *   - "soft-aurora-mesh"     : Organic slow-drifting radial aurora halos (no lines)
 *   - "none"                 : Clear canvas (keeps CSS backdrop untouched)
 */
(function (global) {
  function hexToRgba(hex, alpha) {
    const clean = (hex || "#059669").replace("#", "");
    const r = parseInt(clean.slice(0, 2), 16) || 5;
    const g = parseInt(clean.slice(2, 4), 16) || 150;
    const b = parseInt(clean.slice(4, 6), 16) || 105;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function drawWireframeWave(ctx, w, h, t, accent) {
    const cols = 18, rows = 11;
    const fov = Math.min(w, h) * 1.15;
    const horizonY = h * 0.58;
    const pts = [];
    for (let r = 0; r < rows; r++) {
      const row = [];
      const z = 1.55 + r * 0.50 - ((t * 0.40) % 0.50);
      for (let c = 0; c < cols; c++) {
        const nx = (c / (cols - 1) - 0.5) * 10.5;
        const wave = Math.sin(nx * 0.7 + t * 1.15) * 0.16 + Math.cos(z * 1.0 - t * 0.85) * 0.13;
        row.push([w * 0.5 + (nx / z) * fov, horizonY + ((1.5 + wave) / z) * fov * 0.56]);
      }
      pts.push(row);
    }
    ctx.strokeStyle = hexToRgba(accent, 0.18);
    ctx.lineWidth = 1.5;
    for (let r = 0; r < rows; r++) {
      ctx.beginPath();
      for (let c = 0; c < cols; c++) {
        const [x, y] = pts[r][c];
        c === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    for (let c = 0; c < cols; c++) {
      ctx.beginPath();
      for (let r = 0; r < rows; r++) {
        const [x, y] = pts[r][c];
        r === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  function project3D(p, cx, cy, fov) {
    const z = p[2] + 5.0;
    return [cx + (p[0] / z) * fov, cy + (p[1] / z) * fov];
  }

  function rotXYZ(p, rx, ry, rz) {
    let [x, y, z] = p;
    let c = Math.cos(rx), s = Math.sin(rx);
    [y, z] = [y * c - z * s, y * s + z * c];
    c = Math.cos(ry); s = Math.sin(ry);
    [x, z] = [x * c + z * s, -x * s + z * c];
    c = Math.cos(rz); s = Math.sin(rz);
    [x, y] = [x * c - y * s, x * s + y * c];
    return [x, y, z];
  }

  function drawFloatingPolyhedra(ctx, w, h, t, accent) {
    const cubeV = [
      [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
      [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],
    ];
    const cubeE = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
    const octV = [[0,1.3,0],[0,-1.3,0],[1.1,0,0],[-1.1,0,0],[0,0,1.1],[0,0,-1.1]];
    const octE = [[0,2],[0,3],[0,4],[0,5],[1,2],[1,3],[1,4],[1,5],[2,4],[4,3],[3,5],[5,2]];

    const shapes = [
      { v: cubeV, e: cubeE, cx: w * 0.14, cy: h * 0.24, scale: 0.72, sp: 0.35, off: 0.2 },
      { v: octV,  e: octE,  cx: w * 0.87, cy: h * 0.28, scale: 0.85, sp: -0.42, off: 1.4 },
      { v: octV,  e: octE,  cx: w * 0.16, cy: h * 0.80, scale: 0.65, sp: 0.30, off: 2.6 },
      { v: cubeV, e: cubeE, cx: w * 0.85, cy: h * 0.78, scale: 0.78, sp: -0.32, off: 3.9 },
    ];

    const fov = Math.min(w, h) * 0.45;
    ctx.lineWidth = 1.8;
    for (const sh of shapes) {
      const floatY = Math.sin(t * 0.85 + sh.off) * 18;
      const pts = sh.v.map((pt) => {
        const scaled = [pt[0] * sh.scale, pt[1] * sh.scale, pt[2] * sh.scale];
        const r = rotXYZ(scaled, t * sh.sp + sh.off, t * sh.sp * 1.3, sh.off);
        return project3D(r, sh.cx, sh.cy + floatY, fov);
      });
      ctx.strokeStyle = hexToRgba(accent, 0.22);
      ctx.beginPath();
      for (const [a, b] of sh.e) {
        ctx.moveTo(pts[a][0], pts[a][1]);
        ctx.lineTo(pts[b][0], pts[b][1]);
      }
      ctx.stroke();
      ctx.fillStyle = hexToRgba(accent, 0.36);
      for (const [x, y] of pts) {
        ctx.beginPath();
        ctx.arc(x, y, 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function drawOrbitalRings(ctx, w, h, t, accent) {
    const cx = w * 0.5, cy = h * 0.5;
    const baseR = Math.min(w, h) * 0.34;
    const rings = [
      { r: baseR * 0.85, tiltX: 0.95, tiltY: 0.25, speed: 0.45, alpha: 0.16 },
      { r: baseR * 1.18, tiltX: 1.15, tiltY: -0.35, speed: -0.32, alpha: 0.13 },
      { r: baseR * 1.48, tiltX: 0.75, tiltY: 0.42, speed: 0.22, alpha: 0.10 },
    ];
    for (const rg of rings) {
      ctx.strokeStyle = hexToRgba(accent, rg.alpha);
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      const segs = 72;
      for (let i = 0; i <= segs; i++) {
        const ang = (i / segs) * Math.PI * 2 + t * rg.speed;
        const p = rotXYZ([Math.cos(ang) * rg.r, Math.sin(ang) * rg.r, 0], rg.tiltX, rg.tiltY + t * 0.08, 0);
        const sx = cx + p[0];
        const sy = cy + p[1];
        i === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      }
      ctx.stroke();
      // Glowing orbital node
      const nodeAng = t * rg.speed * 1.8;
      const np = rotXYZ([Math.cos(nodeAng) * rg.r, Math.sin(nodeAng) * rg.r, 0], rg.tiltX, rg.tiltY + t * 0.08, 0);
      ctx.fillStyle = hexToRgba(accent, 0.45);
      ctx.beginPath();
      ctx.arc(cx + np[0], cy + np[1], 5.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawDepthGridParticles(ctx, w, h, t, accent) {
    const count = 42;
    const nodes = [];
    for (let i = 0; i < count; i++) {
      const seed = i * 1.6180339;
      const x = ((Math.sin(seed * 13.7) * 0.5 + 0.5) + t * (0.012 + (i % 3) * 0.004)) % 1.0;
      const y = (Math.cos(seed * 9.3) * 0.5 + 0.5) + Math.sin(t * 0.7 + seed) * 0.02;
      const depth = 0.4 + (i % 5) * 0.15;
      nodes.push([x * w, y * h, depth]);
    }
    ctx.lineWidth = 1.2;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i][0] - nodes[j][0];
        const dy = nodes[i][1] - nodes[j][1];
        const dist = Math.hypot(dx, dy);
        if (dist < 220) {
          ctx.strokeStyle = hexToRgba(accent, (1 - dist / 220) * 0.16);
          ctx.beginPath();
          ctx.moveTo(nodes[i][0], nodes[i][1]);
          ctx.lineTo(nodes[j][0], nodes[j][1]);
          ctx.stroke();
        }
      }
    }
    for (const [x, y, d] of nodes) {
      ctx.fillStyle = hexToRgba(accent, 0.20 + d * 0.25);
      ctx.beginPath();
      ctx.arc(x, y, 2.5 + d * 3.0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawSoftAuroraMesh(ctx, w, h, t, accent, secondary) {
    const blobs = [
      { cx: w * (0.24 + Math.sin(t * 0.35) * 0.08), cy: h * (0.28 + Math.cos(t * 0.28) * 0.07), r: Math.max(w, h) * 0.42, col: accent, a: 0.14 },
      { cx: w * (0.78 + Math.cos(t * 0.30) * 0.08), cy: h * (0.72 + Math.sin(t * 0.25) * 0.07), r: Math.max(w, h) * 0.45, col: secondary || "#0284C7", a: 0.13 },
      { cx: w * (0.52 + Math.sin(t * 0.22 + 1.5) * 0.10), cy: h * (0.55 + Math.cos(t * 0.32) * 0.08), r: Math.max(w, h) * 0.36, col: accent, a: 0.09 },
    ];
    for (const b of blobs) {
      const grad = ctx.createRadialGradient(b.cx, b.cy, 0, b.cx, b.cy, b.r);
      grad.addColorStop(0, hexToRgba(b.col, b.a));
      grad.addColorStop(1, hexToRgba(b.col, 0));
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }
  }

  global.DemoCraftBg = {
    STYLES: [
      "wireframe-wave",
      "floating-polyhedra",
      "orbital-rings",
      "depth-grid-particles",
      "soft-aurora-mesh",
      "none",
    ],
    draw: function (ctx, w, h, t, style, opts) {
      ctx.clearRect(0, 0, w, h);
      const o = opts || {};
      const accent = o.accent || "#059669";
      const secondary = o.secondary || "#0284C7";
      if (style === "none") return;
      if (style === "floating-polyhedra") return drawFloatingPolyhedra(ctx, w, h, t, accent);
      if (style === "orbital-rings") return drawOrbitalRings(ctx, w, h, t, accent);
      if (style === "depth-grid-particles") return drawDepthGridParticles(ctx, w, h, t, accent);
      if (style === "soft-aurora-mesh") return drawSoftAuroraMesh(ctx, w, h, t, accent, secondary);
      return drawWireframeWave(ctx, w, h, t, accent);
    },
  };
})(window);
