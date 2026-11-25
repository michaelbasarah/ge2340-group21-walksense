// WalkSense vector floor plan: draws map/floorplan.json (metres, x east, y north) into an <svg>. No libraries.
// Used by index.html: FloorPlan.load(), FloorPlan.draw(svg, floor, {onFloor}), FloorPlan.xy(floor, place),
// FloorPlan.dotXY(floor, dot, placesPx), FloorPlan.name(floor, place) and FloorPlan.corridor(floor, a, b) (search route). SVG user units are metres;
// the drawing flips y (SVG y points down), so a point (x, y) is drawn at (x, -y).
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (tag, attrs, text) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  };
  const r2 = v => Math.round(v * 100) / 100;
  const P = ([x, y]) => `${r2(x)},${r2(-y)}`;
  const pathOf = polys => polys.map(p => 'M' + p.map(P).join('L') + 'Z').join('');
  const lineOf = pts => 'M' + pts.map(P).join('L');
  let plan = null;
  const view = {};                         // floor -> current viewBox [x, y, w, h] (zoom / pan)

  function load(url) {
    return fetch(url || '/map/floorplan.json').then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(j => { plan = j; return j; });
  }

  const floorOf = f => plan && plan.floors[String(f)];
  function name(floor, id) { const p = floorOf(floor) && floorOf(floor).places[id]; return p ? p.name : null; }
  function xy(floor, id) { const p = floorOf(floor) && floorOf(floor).places[id]; return p ? [p.x, p.y] : null; }

  function lengthOf(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
  function along(pts, d) {                  // point at distance d along a polyline, plus the segment direction
    for (let i = 1; i < pts.length; i++) {
      const [ax, ay] = pts[i - 1], [bx, by] = pts[i], L = Math.hypot(bx - ax, by - ay);
      if (d <= L || i === pts.length - 1) { const t = L ? Math.min(1, Math.max(0, d / L)) : 0; return { x: ax + t * (bx - ax), y: ay + t * (by - ay), dx: bx - ax, dy: by - ay }; }
      d -= L;
    }
    return { x: pts[0][0], y: pts[0][1], dx: 1, dy: 0 };
  }
  function corridor(floor, a, b) {           // polyline from place a to place b (reversed if stored b -> a)
    const F = floorOf(floor); if (!F) return null;
    for (const e of F.edges) {
      if (e.from === a && e.to === b) return e.points;
      if (e.from === b && e.to === a) return e.points.slice().reverse();
    }
    const A = xy(floor, a), B = xy(floor, b);
    return A && B ? [A, B] : null;
  }

  // route.py's walking dot is in places.json pixels: {x, y, from, to}. Its position is a straight interpolation
  // between the two places' pixels, so the fraction is recovered by projection and replayed along the corridor here.
  function dotXY(floor, dot, placesPx) {
    if (!plan || !dot) return null;
    const px = placesPx && placesPx[String(floor)] && placesPx[String(floor)].places;
    const pts = corridor(floor, dot.from, dot.to);
    if (pts && px && px[dot.from] && px[dot.to]) {
      const a = px[dot.from], b = px[dot.to], vx = b.x - a.x, vy = b.y - a.y, L2 = vx * vx + vy * vy;
      const t = L2 ? Math.min(1, Math.max(0, ((dot.x - a.x) * vx + (dot.y - a.y) * vy) / L2)) : 0;
      const p = along(pts, t * lengthOf(pts));
      return [p.x, p.y];
    }
    const m = plan.px_to_m && plan.px_to_m[String(floor)];   // fallback: affine fit of the old pixel frame
    return m ? [m.matrix[0][0] * dot.x + m.matrix[0][1] * dot.y + m.matrix[0][2], m.matrix[1][0] * dot.x + m.matrix[1][1] * dot.y + m.matrix[1][2]] : null;
  }

  function fullBox(F) { const [x0, y0, x1, y1] = F.bounds; return [x0, -y1, x1 - x0, y1 - y0]; }

  function draw(svg, floor, opts) {
    opts = opts || {};
    const F = floorOf(floor);
    if (!F) return false;
    const vb = view[floor] || (view[floor] = fullBox(F));
    svg.setAttribute('viewBox', vb.map(r2).join(' '));
    svg.setAttribute('class', 'plan');
    const s = vb[2] / 40;                                           // on-screen unit: texts keep their size when zoomed
    const fs = k => ({ style: `font-size:${r2(k * s)}px` });
    const [bx0, by0, bx1, by1] = F.bounds;
    const g = mk('g');
    g.append(mk('rect', { x: bx0 - 50, y: -by1 - 50, width: bx1 - bx0 + 100, height: by1 - by0 + 100, class: 'fp-out' }));
    // Google context: corridors (white), then every traced block, then the named footprints
    g.append(mk('path', { d: pathOf(F.walkable), class: 'fp-walk', 'fill-rule': 'evenodd' }));
    for (const e of F.edges) g.append(mk('path', { d: lineOf(e.points), class: 'fp-corridor' }));
    for (const c of F.context) g.append(mk('path', { d: pathOf([c.poly]), class: 'fp-ctx fp-' + c.kind }));
    for (const r of F.rooms) {
      const shape = mk('path', { d: pathOf(r.polys), class: 'fp-room fp-k-' + r.kind });
      shape.append(mk('title', {}, r.label + (r.note ? ` (${r.note})` : '')));
      g.append(shape);
    }
    // corridor centrelines with their length (solid = measured, dashed = steps x 0.54 m, dotted = guess)
    for (const e of F.edges) {
      g.append(mk('path', { d: lineOf(e.points), class: 'fp-edge fp-src-' + e.source }));
      const L = lengthOf(e.points), m = along(e.points, L / 2);
      let ang = Math.atan2(-m.dy, m.dx) * 180 / Math.PI;           // SVG angle (y flipped)
      if (ang > 90) ang -= 180; if (ang <= -90) ang += 180;
      const lx = m.x, ly = m.y;                                    // on the line; its halo hides the line behind it
      const txt = (e.source === 'measured' ? '' : '~') + e.metres.toFixed(1) + ' m' + (e.source === 'guess' ? '?' : '');
      const t = mk('text', { x: r2(lx), y: r2(-ly), class: 'fp-len fp-src-' + e.source, 'text-anchor': 'middle', 'dominant-baseline': 'central', transform: `rotate(${r2(ang)} ${r2(lx)} ${r2(-ly)})`, ...fs(0.85) }, txt);
      t.append(mk('title', {}, `${name(floor, e.from)} - ${name(floor, e.to)}: ${e.metres} m (${e.source}: ${e.source_detail}); drawn ${e.drawn_m} m` + (e.sketch_mark_m ? `; sketch mark ${e.sketch_mark_m} m` : '')));
      g.append(t);
    }
    // block labels that are not a place name (e.g. City Express, Escalators, Stairs)
    for (const r of F.rooms) {
      if (r.place && F.places[r.place]) continue;                  // the place label already names it
      const big = r.polys.reduce((a, b) => (b.length > a.length ? b : a));
      const cx = big.reduce((s, q) => s + q[0], 0) / big.length, cy = big.reduce((s, q) => s + q[1], 0) / big.length;
      const [x0, y0, x1, y1] = F.bounds;
      if (cx < x0 || cx > x1 || cy < y0 || cy > y1) continue;
      g.append(mk('text', { x: r2(cx), y: r2(-cy), class: 'fp-blocklabel', 'text-anchor': 'middle', ...fs(0.85) }, r.label.replace(/ \(.*\)$/, '')));
    }
    // places: marker + short label, pushed away from the middle of the floor
    const ids = Object.keys(F.places);
    const mx = ids.reduce((s, k) => s + F.places[k].x, 0) / ids.length, my = ids.reduce((s, k) => s + F.places[k].y, 0) / ids.length;
    for (const id of ids) {
      const p = F.places[id];
      const c = mk('circle', { cx: r2(p.x), cy: r2(-p.y), r: r2(Math.max(0.35, 0.4 * s)), class: 'fp-place fp-k-' + p.kind + (p.inferred ? ' fp-inferred' : '') });
      c.append(mk('title', {}, `${p.name}: ${p.status}`));
      g.append(c);
      let dx = p.x - mx, dy = p.y - my; const n = Math.hypot(dx, dy) || 1; dx /= n; dy /= n;
      if (p.label_dx != null) { dx = p.label_dx; dy = p.label_dy; }
      const lx = p.x + dx * 0.8 * s, ly = p.y + dy * 0.8 * s - (dy < -0.35 ? 0.5 * s : 0);
      const text = p.short + (p.inferred ? '*' : ''), wid = 0.62 * 1.05 * s * text.length;
      let anchor = dx > 0.35 ? 'start' : dx < -0.35 ? 'end' : 'middle';
      if (anchor === 'end' && lx - wid < vb[0]) anchor = 'start';          // keep the label inside the view
      else if (anchor === 'start' && lx + wid > vb[0] + vb[2]) anchor = 'end';
      else if (anchor === 'middle' && lx - wid / 2 < vb[0]) anchor = 'start';
      else if (anchor === 'middle' && lx + wid / 2 > vb[0] + vb[2]) anchor = 'end';
      const t = mk('text', { x: r2(lx), y: r2(-ly + 0.35 * s), class: 'fp-label', 'data-place': id, 'text-anchor': anchor, ...fs(1.05) }, text);
      t.append(mk('title', {}, p.name));
      g.append(t);
    }
    // escalators and lift/stairs: arrow badge that links to the other floor
    for (const l of F.links) {
      const p = F.places[l.place]; if (!p) continue;
      const arrow = l.mode === 'lift_stairs' ? '⇅' : (l.direction === 'up' ? '▲' : '▼');
      const label = l.mode === 'lift_stairs' ? `${arrow} ${l.to_floor}F` : l.leaves_here ? `${arrow} to ${l.to_floor}F` : `${arrow} from ${l.to_floor}F`;
      let dx = p.x - mx, dy = p.y - my; const n = Math.hypot(dx, dy) || 1; dx /= n; dy /= n;
      const bx = p.x - dx * 1.5 * s, by = p.y - dy * 1.5 * s;
      const b = mk('g', { class: 'fp-link', role: 'button', tabindex: 0, 'aria-label': `${p.name}: ${l.mode.replace('_', ' and ')} ${l.leaves_here ? 'to' : 'from'} ${l.to_floor}F. Show ${l.to_floor}F` });
      const w = (0.55 * label.length + 0.8) * s;
      b.append(mk('rect', { x: r2(bx - w / 2), y: r2(-by - 0.75 * s), width: r2(w), height: r2(1.5 * s), rx: r2(0.75 * s), class: 'fp-linkbg' }));
      b.append(mk('text', { x: r2(bx), y: r2(-by + 0.33 * s), 'text-anchor': 'middle', class: 'fp-linktext', ...fs(0.95) }, label));
      b.append(mk('title', {}, `${l.mode === 'escalator' ? 'Escalator' : 'Lift / stairs'} ${l.one_way ? '(one way) ' : ''}${l.leaves_here ? 'to' : 'from'} ${l.to_floor}F, about ${l.seconds} s (${l.seconds_status}). Tap to show ${l.to_floor}F.`));
      const go = ev => { ev.preventDefault(); ev.stopPropagation(); if (opts.onFloor) opts.onFloor(l.to_floor); };
      b.addEventListener('click', go);
      b.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') go(ev); });
      g.append(b);
    }
    // scale bar (5 m) bottom left and north arrow top right, both in the fixed corner of the current view
    const sx = vb[0] + 1.5 * s, sy = vb[1] + vb[3] - 1.6 * s, len = 5;
    const sb = mk('g', { class: 'fp-scale' });
    sb.append(mk('path', { d: `M${r2(sx)},${r2(sy - 0.5 * s)}V${r2(sy)}H${r2(sx + len)}V${r2(sy - 0.5 * s)}`, class: 'fp-scaleline' }));
    sb.append(mk('text', { x: r2(sx + len + 0.6 * s), y: r2(sy), class: 'fp-scaletext', style: `font-size:${r2(1.1 * s)}px` }, '5 m'));
    g.append(sb);
    if (plan.frame && plan.frame.north_deg != null) {
      const nx = vb[0] + vb[2] - 2 * s, ny = vb[1] + 3.4 * s, h = 1.5 * s;
      const na = mk('g', { class: 'fp-north', transform: `rotate(${-plan.frame.north_deg} ${r2(nx)} ${r2(ny)})` });
      na.append(mk('path', { d: `M${r2(nx)},${r2(ny - h)}L${r2(nx + 0.6 * s)},${r2(ny + 0.6 * s)}L${r2(nx)},${r2(ny + 0.2 * s)}L${r2(nx - 0.6 * s)},${r2(ny + 0.6 * s)}Z` }));
      na.append(mk('text', { x: r2(nx), y: r2(ny - h - 0.35 * s), 'text-anchor': 'middle', style: `font-size:${r2(1.2 * s)}px` }, 'N'));
      na.append(mk('title', {}, 'North: ' + plan.frame.north_source));
      g.append(na);
    }
    svg.replaceChildren(g);
    return true;
  }

  // zoom (buttons / wheel) and drag to pan, per floor; draw() must be called again after a change
  function zoom(floor, factor, cx, cy) {
    const F = floorOf(floor); if (!F) return;
    const full = fullBox(F), vb = view[floor] || full.slice();
    const w = Math.min(full[2], Math.max(full[2] / 6, vb[2] * factor)), h = w * full[3] / full[2];
    cx = cx == null ? vb[0] + vb[2] / 2 : cx; cy = cy == null ? vb[1] + vb[3] / 2 : cy;
    view[floor] = clamp(full, [cx - (cx - vb[0]) * w / vb[2], cy - (cy - vb[1]) * h / vb[3], w, h]);
  }
  function pan(floor, dx, dy) { const F = floorOf(floor); if (!F || !view[floor]) return; const vb = view[floor]; view[floor] = clamp(fullBox(F), [vb[0] - dx, vb[1] - dy, vb[2], vb[3]]); }
  function reset(floor) { delete view[floor]; }
  function zoomed(floor) { const F = floorOf(floor); return !!(F && view[floor] && view[floor][2] < fullBox(F)[2] - 1e-6); }
  function clamp(full, vb) {
    vb[0] = Math.min(Math.max(vb[0], full[0]), full[0] + full[2] - vb[2]);
    vb[1] = Math.min(Math.max(vb[1], full[1]), full[1] + full[3] - vb[3]);
    return vb;
  }
  function center(floor, x, y) {             // keep a point in view when zoomed in (the walking dot)
    const vb = view[floor], F = floorOf(floor); if (!vb || !F || !zoomed(floor)) return;
    const X = x, Y = -y, m = 0.15;
    if (X < vb[0] + m * vb[2] || X > vb[0] + (1 - m) * vb[2] || Y < vb[1] + m * vb[3] || Y > vb[1] + (1 - m) * vb[3])
      view[floor] = clamp(fullBox(F), [X - vb[2] / 2, Y - vb[3] / 2, vb[2], vb[3]]);
  }

  function unit(floor) { const F = floorOf(floor); return F ? (view[floor] || fullBox(F))[2] / 40 : 1; }

  window.FloorPlan = { load, draw, xy, name, dotXY, corridor, zoom, pan, reset, zoomed, center, unit, get plan() { return plan; } };
})();
