<script lang="ts">
  /**
   * TacticalMap — canvas-based tactical display.
   *
   * Rewritten to match the prototype in tools/design_reference_v2.html:
   *   • Dark vignette + starfield
   *   • Range rings & grid
   *   • IFF-coded contact shapes (square / diamond / dashed circle)
   *   • Velocity vectors, targeting brackets, firing solution cone
   *   • Trajectory projection along own-ship velocity
   *   • Compass rose and scale label
   *   • Toolbar with scale zoom and flag toggles (V/G/S/T/A)
   *
   * Data wiring is preserved from the previous implementation — we still read
   * from gameState + selectedTacticalTargetId and use tacticalData.ts helpers.
   */
  import { onDestroy, onMount, tick } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getTacticalContacts,
    getBestWeaponSolution,
    getLockedTargetId,
    getTargetingSummary,
    type TacticalContact,
  } from "./tacticalData.js";
  import { lockTarget } from "./tacticalActions.js";
  import { getOrientation, getPosition, getVelocity, toNumber } from "../helm/helmData.js";

  // ── State ──────────────────────────────────────────────────────────────
  let canvas: HTMLCanvasElement;
  let container: HTMLDivElement;
  let dims = { w: 400, h: 400 };
  let scale = 90000; // meters radius
  const scaleSteps = [5000, 10000, 25000, 50000, 100000, 200000, 400000, 800000];
  let flags = {
    vectors: true,
    grid: true,
    solutions: true,
    traj: true,
    arcs: false,
    auto: true,
  };
  let stars: Array<{ x: number; y: number; r: number; a: number }> = [];
  let pinging = false;
  let rafId: number | null = null;
  let lockBusy = false;
  let viewCenter = { x: 0, y: 0 };
  let pointerId: number | null = null;
  let pointerDown = false;
  let dragMoved = false;
  let suppressClick = false;
  let dragStart = { x: 0, y: 0 };
  let dragOrigin = { x: 0, y: 0 };

  // ── Reactive data from gameState ──────────────────────────────────────
  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: shipPos = getPosition(ship);
  $: shipVel = getVelocity(ship);
  $: shipHeading = getOrientation(ship).yaw; // degrees
  $: targeting = getTargetingSummary(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: bestSolution = getBestWeaponSolution(ship);
  $: selectedId = $selectedTacticalTargetId;
  $: if (flags.auto || (!pointerDown && viewCenter.x === 0 && viewCenter.y === 0)) {
    if (Math.abs(viewCenter.x - shipPos.x) > 0.01 || Math.abs(viewCenter.y - shipPos.y) > 0.01) {
      viewCenter = { x: shipPos.x, y: shipPos.y };
    }
  }

  // Generate stars once
  onMount(() => {
    stars = Array.from({ length: 120 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 0.9 + 0.2,
      a: Math.random() * 0.5 + 0.1,
    }));

    const obs = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      dims = { w: Math.max(100, rect.width), h: Math.max(100, rect.height) };
    });
    if (container) obs.observe(container);

    // Animation loop (drives starfield-twinkle, pulses, radar sweep)
    const loop = () => {
      draw();
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);

    return () => {
      obs.disconnect();
      if (rafId != null) cancelAnimationFrame(rafId);
    };
  });

  onDestroy(() => {
    if (rafId != null) cancelAnimationFrame(rafId);
  });

  // Trigger redraw when reactive data changes
  $: if (canvas && dims.w) {
    void dims;
    void contacts;
    void shipPos;
    void shipVel;
    void shipHeading;
    void targeting;
    void selectedId;
    void scale;
    void flags;
    // draw is called each RAF — nothing to do here; this block just keeps
    // reactivity alive so Svelte re-evaluates when props change.
  }

  // ── Helpers ────────────────────────────────────────────────────────────
  function iffColor(contact: TacticalContact): string {
    const dip = contact.diplomaticState.toLowerCase();
    if (dip.includes("hostile") || contact.threatLevel === "red") return "#e83030";
    if (dip.includes("friend") || dip.includes("allied")) return "#00dd6a";
    if (dip.includes("unknown") || !dip) return "#efa020";
    return "#6888aa";
  }

  function iffKind(contact: TacticalContact): "hostile" | "friendly" | "unknown" | "neutral" {
    const dip = contact.diplomaticState.toLowerCase();
    if (dip.includes("hostile") || contact.threatLevel === "red" || contact.threatLevel === "orange") return "hostile";
    if (dip.includes("friend") || dip.includes("allied")) return "friendly";
    if (dip.includes("unknown") || dip === "") return "unknown";
    return "neutral";
  }

  function isOrdnance(contact: TacticalContact): boolean {
    return /torpedo|missile|ordnance/i.test(contact.classification);
  }

  function autoScaleFit(): number {
    if (!flags.auto || !contacts.length) return scale;
    let mx = 0;
    for (const c of contacts) if (c.distance > mx) mx = c.distance;
    const fit = scaleSteps.find((o) => o >= mx * 1.3);
    return fit ?? scaleSteps[scaleSteps.length - 1];
  }

  function mod(value: number, divisor: number): number {
    return ((value % divisor) + divisor) % divisor;
  }

  function pixelsPerMeter(activeScale: number): number {
    return Math.min(dims.w, dims.h) / 2 / activeScale;
  }

  function worldToScreen(worldX: number, worldY: number, ppm: number, cx: number, cy: number) {
    return {
      x: cx + (worldX - viewCenter.x) * ppm,
      y: cy - (worldY - viewCenter.y) * ppm,
    };
  }

  function screenToWorld(screenX: number, screenY: number, ppm: number, cx: number, cy: number) {
    return {
      x: viewCenter.x + (screenX - cx) / ppm,
      y: viewCenter.y - (screenY - cy) / ppm,
    };
  }

  // ── Drawing ────────────────────────────────────────────────────────────
  function draw() {
    if (!canvas || !dims.w) return;
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== dims.w * dpr || canvas.height !== dims.h * dpr) {
      canvas.width = dims.w * dpr;
      canvas.height = dims.h * dpr;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    const w = dims.w;
    const h = dims.h;
    const cx = w / 2;
    const cy = h / 2;
    const t = Date.now();

    const sc = autoScaleFit();
    const ppm = pixelsPerMeter(sc);
    const shipScreen = worldToScreen(shipPos.x, shipPos.y, ppm, cx, cy);

    // Background
    ctx.fillStyle = "#020207";
    ctx.fillRect(0, 0, w, h);
    const vig = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.8);
    vig.addColorStop(0, "rgba(14,14,30,.05)");
    vig.addColorStop(1, "rgba(0,0,4,.72)");
    ctx.fillStyle = vig;
    ctx.fillRect(0, 0, w, h);

    // Starfield
    for (const s of stars) {
      ctx.beginPath();
      ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(180,190,220,${s.a})`;
      ctx.fill();
    }

    // Grid
    if (flags.grid) {
      const gPx = (sc / 4) * ppm;
      ctx.strokeStyle = "rgba(24,24,52,.55)";
      ctx.lineWidth = 1;
      if (gPx > 6) {
        for (let x = mod(cx - viewCenter.x * ppm, gPx); x < w; x += gPx) {
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, h);
          ctx.stroke();
        }
        for (let y = mod(cy + viewCenter.y * ppm, gPx); y < h; y += gPx) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
          ctx.stroke();
        }
      }
      ctx.strokeStyle = "rgba(40,40,80,.4)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx - 8, cy);
      ctx.lineTo(cx + 8, cy);
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx, cy + 8);
      ctx.stroke();
    }

    // Range rings (50% & 100% of scale)
    for (const [frac, col] of [
      [0.5, "rgba(28,110,200,.14)"] as const,
      [1.0, "rgba(28,110,200,.2)"] as const,
    ]) {
      const r = sc * frac * ppm;
      ctx.beginPath();
      ctx.arc(shipScreen.x, shipScreen.y, r, 0, Math.PI * 2);
      ctx.strokeStyle = col;
      ctx.lineWidth = frac === 1 ? 1.5 : 1;
      ctx.stroke();
      const labelM = sc * frac;
      const lbl = labelM >= 1000 ? `${(labelM / 1000).toFixed(0)}km` : `${labelM.toFixed(0)}m`;
      ctx.fillStyle = "rgba(40,100,200,.4)";
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      ctx.fillText(lbl, shipScreen.x + r * Math.cos(-Math.PI * 0.45) + 3, shipScreen.y + r * Math.sin(-Math.PI * 0.45));
    }

    // Radar sweep when pinging
    if (pinging) {
      const sa = (t / 420) % (Math.PI * 2);
      ctx.save();
      ctx.translate(shipScreen.x, shipScreen.y);
      ctx.rotate(sa);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, sc * ppm, -0.4, 0);
      ctx.closePath();
      ctx.fillStyle = "rgba(0,190,130,.07)";
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -Math.min(w, h) * 0.5);
      ctx.strokeStyle = "rgba(0,200,140,.5)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.restore();
    }

    // Trajectory projection (dashed line along own-ship velocity)
    if (flags.traj) {
      const vx = shipVel.x;
      const vy = shipVel.y;
      const vmag = Math.sqrt(vx * vx + vy * vy);
      if (vmag > 0.1) {
        ctx.save();
        ctx.setLineDash([3, 5]);
        ctx.strokeStyle = "rgba(30,120,220,.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(shipScreen.x, shipScreen.y);
        for (let i = 1; i <= 20; i++) {
          const ft = (60 / 20) * i; // 60s projection in 20 steps
          const sx = shipScreen.x + vx * ft * ppm;
          const sy = shipScreen.y - vy * ft * ppm;
          if (sx < -30 || sx > w + 30 || sy < -30 || sy > h + 30) break;
          ctx.lineTo(sx, sy);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
    }

    // Firing solution cone
    if (flags.solutions && targeting.lockState === "locked" && lockedTargetId) {
      const tgt = contacts.find((c) => c.id === lockedTargetId);
      if (tgt) {
        // In game coords, contact.position is relative to ship? Or absolute?
        // tacticalData normalizes via contact.position from item.position.
        // We draw relative to own ship, so use (tgt.position - shipPos).
        const dx = tgt.position.x - shipPos.x;
        const dy = tgt.position.y - shipPos.y;
        const ang = Math.atan2(dx, -dy);
        const conf = toNumber(bestSolution.confidence, targeting.lockQuality);
        const ha = ((1 - conf) * 18 + 2) * Math.PI / 180;
        const clen = Math.sqrt(dx * dx + dy * dy) * ppm;
        ctx.save();
        ctx.translate(shipScreen.x, shipScreen.y);
        ctx.rotate(ang);
        const cg = ctx.createLinearGradient(0, 0, 0, -clen);
        cg.addColorStop(0, `rgba(240,150,0,${0.06 + conf * 0.09})`);
        cg.addColorStop(1, "rgba(240,150,0,0)");
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(Math.sin(ha) * clen, -clen);
        ctx.lineTo(-Math.sin(ha) * clen, -clen);
        ctx.closePath();
        ctx.fillStyle = cg;
        ctx.fill();
        ctx.strokeStyle = "rgba(240,150,0,.28)";
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(Math.sin(ha) * clen, -clen);
        ctx.moveTo(0, 0);
        ctx.lineTo(-Math.sin(ha) * clen, -clen);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
    }

    // Contacts
    for (const c of contacts) {
      const { x: sx, y: sy } = worldToScreen(c.position.x, c.position.y, ppm, cx, cy);
      if (sx < -30 || sx > w + 30 || sy < -30 || sy > h + 30) continue;

      const kind = iffKind(c);
      const col = iffColor(c);
      const al = 0.38 + c.confidence * 0.62;
      const ordnance = isOrdnance(c);

      // Velocity vector
      if (flags.vectors && (c.velocity.x || c.velocity.y)) {
        const vx = c.velocity.x * ppm * 14;
        const vy = -c.velocity.y * ppm * 14;
        if (Math.sqrt(vx * vx + vy * vy) > 2) {
          ctx.strokeStyle = col;
          ctx.lineWidth = 1;
          ctx.globalAlpha = al * 0.5;
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(sx + vx, sy + vy);
          ctx.stroke();
        }
      }

      ctx.globalAlpha = al;
      ctx.strokeStyle = col;
      ctx.fillStyle = col;

      // IFF shape
      if (kind === "hostile") {
        if (ordnance) {
          const ps = 5 + Math.sin(t / 200) * 0.5;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(sx, sy - ps);
          ctx.lineTo(sx + ps, sy);
          ctx.lineTo(sx, sy + ps);
          ctx.lineTo(sx - ps, sy);
          ctx.closePath();
          ctx.stroke();
          ctx.globalAlpha = al * 0.4;
          ctx.fill();
        } else {
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.rect(sx - 8, sy - 8, 16, 16);
          ctx.stroke();
          ctx.globalAlpha = al * 0.15;
          ctx.fill();
        }
      } else if (kind === "friendly") {
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(sx, sy - 9);
        ctx.lineTo(sx + 9, sy);
        ctx.lineTo(sx, sy + 9);
        ctx.lineTo(sx - 9, sy);
        ctx.closePath();
        ctx.stroke();
        ctx.globalAlpha = al * 0.2;
        ctx.fill();
      } else if (kind === "unknown") {
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.arc(sx, sy, 8, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = al;
        ctx.font = "bold 8px 'JetBrains Mono', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("?", sx, sy + 1);
      } else {
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(sx, sy, 6, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Targeting brackets
      const isLocked = targeting.lockState === "locked" && c.id === lockedTargetId;
      const isAcquiring = (targeting.lockState === "acquiring" || targeting.lockState === "tracking" || targeting.lockState === "designated") && c.id === (lockedTargetId || selectedId);
      if (isLocked || isAcquiring) {
        const pulse = isLocked ? 1 + Math.sin(t / 700) * 0.04 : 1;
        const bs = (isLocked ? 14 : 18) * pulse;
        const bc = isLocked ? "rgba(255,255,255,.88)" : "rgba(240,160,0,.7)";
        ctx.strokeStyle = bc;
        ctx.lineWidth = isLocked ? 1.5 : 1;
        if (isAcquiring) ctx.setLineDash([3, 2]);
        ctx.beginPath();
        // Four corner brackets
        ctx.moveTo(sx - bs, sy - bs + 5);
        ctx.lineTo(sx - bs, sy - bs);
        ctx.lineTo(sx - bs + 5, sy - bs);
        ctx.moveTo(sx + bs - 5, sy - bs);
        ctx.lineTo(sx + bs, sy - bs);
        ctx.lineTo(sx + bs, sy - bs + 5);
        ctx.moveTo(sx + bs, sy + bs - 5);
        ctx.lineTo(sx + bs, sy + bs);
        ctx.lineTo(sx + bs - 5, sy + bs);
        ctx.moveTo(sx - bs + 5, sy + bs);
        ctx.lineTo(sx - bs, sy + bs);
        ctx.lineTo(sx - bs, sy + bs - 5);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Labels
      ctx.globalAlpha = al * 0.9;
      const labelCol: Record<string, string> = {
        hostile: "#ff7070",
        friendly: "#44ff99",
        unknown: "#ffcc66",
        neutral: "#aabbc8",
      };
      ctx.fillStyle = labelCol[kind] || "#aaa";
      ctx.font = "600 9px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(c.id, sx + 14, sy - 4);
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.globalAlpha = al * 0.55;
      const dStr = c.distance >= 1000 ? `${(c.distance / 1000).toFixed(0)}km` : `${Math.round(c.distance)}m`;
      ctx.fillText(`${String(Math.round(c.bearing)).padStart(3, "0")}° ${dStr}`, sx + 14, sy + 6);
      ctx.globalAlpha = 1;
    }

    // Player ship
    ctx.save();
    ctx.translate(shipScreen.x, shipScreen.y);
    const hdgRad = (shipHeading - 90) * Math.PI / 180;

    // Velocity vector
    if (flags.vectors) {
      const vx = shipVel.x * ppm * 13;
      const vy = -shipVel.y * ppm * 13;
      if (Math.sqrt(vx * vx + vy * vy) > 2) {
        ctx.strokeStyle = "#00dd6a";
        ctx.lineWidth = 2;
        ctx.globalAlpha = 0.75;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(vx, vy);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }

    // Heading line
    ctx.strokeStyle = "rgba(30,140,255,.65)";
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.7;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(hdgRad) * 38, Math.sin(hdgRad) * 38);
    ctx.stroke();
    ctx.globalAlpha = 1;

    // Ship triangle
    ctx.rotate(hdgRad + Math.PI / 2);
    ctx.fillStyle = "#1e8cff";
    ctx.beginPath();
    ctx.moveTo(0, -10);
    ctx.lineTo(-6, 8);
    ctx.lineTo(6, 8);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(120,180,255,.8)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();

    // Compass rose
    const cr = 22;
    const cxR = w - 34;
    const cyR = 34;
    ctx.save();
    ctx.translate(cxR, cyR);
    ctx.strokeStyle = "#2e2e50";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(0, 0, cr, 0, Math.PI * 2);
    ctx.stroke();
    const dirs = ["N", "E", "S", "W"];
    dirs.forEach((d, i) => {
      const a = i * Math.PI / 2;
      const r = cr - 7;
      ctx.fillStyle = d === "N" ? "#4499ff" : "#3a3a52";
      ctx.font = "bold 7px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(d, Math.cos(a) * r, Math.sin(a) * r);
    });
    const hr = (shipHeading - 90) * Math.PI / 180;
    ctx.strokeStyle = "#4499ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(hr) * cr * 0.72, Math.sin(hr) * cr * 0.72);
    ctx.stroke();
    ctx.fillStyle = "#4499ff";
    ctx.font = "600 7px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${String(Math.round(shipHeading < 0 ? shipHeading + 360 : shipHeading)).padStart(3, "0")}°`, 0, 0);
    ctx.restore();

    // Scale label
    const sl = sc >= 1000 ? `${(sc / 1000).toFixed(0)} km radius` : `${sc} m radius`;
    ctx.fillStyle = "#3a3a52";
    ctx.font = "9px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(sl, 8, h - 8);
  }

  // ── Toolbar actions ────────────────────────────────────────────────────
  function zoom(dir: 1 | -1) {
    const i = scaleSteps.findIndex((v) => v === scale);
    const pi = i === -1 ? scaleSteps.findIndex((v) => v >= scale) : i;
    // "+" = zoom in = smaller scale. "−" = zoom out = larger scale.
    const next = dir > 0 ? pi - 1 : pi + 1;
    if (next >= 0 && next < scaleSteps.length) {
      scale = scaleSteps[next];
      flags = { ...flags, auto: false };
    }
  }

  function zoomAt(dir: 1 | -1, screenX = dims.w / 2, screenY = dims.h / 2) {
    const i = scaleSteps.findIndex((v) => v === scale);
    const pi = i === -1 ? scaleSteps.findIndex((v) => v >= scale) : i;
    const next = dir > 0 ? pi - 1 : pi + 1;
    if (next < 0 || next >= scaleSteps.length) return;

    const currentPpm = pixelsPerMeter(scale);
    const anchor = screenToWorld(screenX, screenY, currentPpm, dims.w / 2, dims.h / 2);
    const nextScale = scaleSteps[next];
    const nextPpm = pixelsPerMeter(nextScale);

    scale = nextScale;
    flags = { ...flags, auto: false };
    viewCenter = {
      x: anchor.x - (screenX - dims.w / 2) / nextPpm,
      y: anchor.y + (screenY - dims.h / 2) / nextPpm,
    };
  }

  function toggleFlag(k: keyof typeof flags) {
    const next = !flags[k];
    flags = { ...flags, [k]: next };
    if (k === "auto" && next) {
      viewCenter = { x: shipPos.x, y: shipPos.y };
    }
  }

  function recenterOnShip() {
    viewCenter = { x: shipPos.x, y: shipPos.y };
  }

  async function onLockSelected() {
    if (!selectedId || lockBusy) return;
    lockBusy = true;
    try {
      await lockTarget(selectedId);
    } finally {
      lockBusy = false;
    }
  }

  // Canvas click → select nearest contact
  function onCanvasClick(e: MouseEvent) {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const cx = dims.w / 2;
    const cy = dims.h / 2;
    const sc = autoScaleFit();
    const ppm = pixelsPerMeter(sc);

    let closest: { id: string; d: number } | null = null;
    for (const c of contacts) {
      const { x: sx, y: sy } = worldToScreen(c.position.x, c.position.y, ppm, cx, cy);
      const dx = sx - mx;
      const dy = sy - my;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < 18 && (!closest || d < closest.d)) {
        closest = { id: c.id, d };
      }
    }
    if (closest) {
      selectedTacticalTargetId.set(closest.id);
    }
  }

  function pointerToLocal(event: MouseEvent | PointerEvent | WheelEvent) {
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  function onPointerDown(event: PointerEvent) {
    if (!canvas) return;
    pointerId = event.pointerId;
    pointerDown = true;
    dragMoved = false;
    const point = pointerToLocal(event);
    dragStart = point;
    dragOrigin = { ...viewCenter };
    canvas.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent) {
    if (!pointerDown || pointerId !== event.pointerId) return;
    const point = pointerToLocal(event);
    const dx = point.x - dragStart.x;
    const dy = point.y - dragStart.y;
    if (!dragMoved && Math.hypot(dx, dy) > 4) {
      dragMoved = true;
    }
    if (!dragMoved) return;

    const ppm = pixelsPerMeter(scale);
    viewCenter = {
      x: dragOrigin.x - dx / ppm,
      y: dragOrigin.y + dy / ppm,
    };
    if (flags.auto) {
      flags = { ...flags, auto: false };
    }
  }

  function releasePointer(event: PointerEvent) {
    if (!pointerDown || pointerId !== event.pointerId) return;
    if (canvas?.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
    pointerDown = false;
    pointerId = null;
    suppressClick = dragMoved;
  }

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    const point = pointerToLocal(event);
    zoomAt(event.deltaY < 0 ? 1 : -1, point.x, point.y);
  }
</script>

<Panel title="Tactical Display" domain="sensor" priority="primary" className="tactical-map-panel">
  <div class="map-root">
    <!-- Toolbar -->
    <div class="toolbar">
      <span class="tb-lbl">SCALE</span>
      <button class="tb-btn small" on:click={() => zoom(-1)} title="Zoom out">−</button>
      <button class="tb-btn small" on:click={() => zoom(1)} title="Zoom in">+</button>
      <div class="tb-sep"></div>
      <button class="tb-btn small" class:on={flags.vectors} on:click={() => toggleFlag("vectors")} title="Toggle velocity vectors">V</button>
      <button class="tb-btn small" class:on={flags.grid} on:click={() => toggleFlag("grid")} title="Toggle grid">G</button>
      <button class="tb-btn small" class:on={flags.solutions} on:click={() => toggleFlag("solutions")} title="Toggle firing solution cone">S</button>
      <button class="tb-btn small" class:on={flags.traj} on:click={() => toggleFlag("traj")} title="Toggle trajectory projection">T</button>
      <button class="tb-btn small" class:on={flags.auto} on:click={() => toggleFlag("auto")} title="Auto-scale to contacts">A</button>
      <button class="tb-btn small" on:click={recenterOnShip} title="Recenter camera on own ship">Ship</button>

      <div class="tb-spacer"></div>

      <button
        class="tb-btn"
        disabled={!selectedId || lockBusy}
        title={!selectedId ? "Select a contact to lock" : lockBusy ? "Locking…" : "Lock selected as target"}
        on:click={onLockSelected}
      >
        {lockBusy ? "LOCKING…" : "LOCK"}
      </button>
    </div>

    <div bind:this={container} class="canvas-wrap" class:lock-busy={lockBusy} class:dragging={pointerDown && dragMoved}>
      <canvas
        bind:this={canvas}
        on:click={onCanvasClick}
        on:pointerdown={onPointerDown}
        on:pointermove={onPointerMove}
        on:pointerup={releasePointer}
        on:pointercancel={releasePointer}
        on:wheel={onWheel}
      ></canvas>
      {#if pinging}
        <div class="ping-ring"></div>
      {/if}
    </div>
  </div>
</Panel>

<style>
  :global(.tactical-map-panel .panel-body) {
    display: flex;
    min-height: 0;
    overflow: hidden;
    padding: 0;
  }

  .map-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    flex: 1 1 auto;
    min-height: 0;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 4px 8px;
    border-bottom: 1px solid var(--bd-subtle);
    background: rgba(0, 0, 0, 0.2);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .tb-lbl {
    font-size: 0.55rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .tb-btn {
    background: transparent;
    border: 1px solid var(--bd-default);
    color: var(--tx-sec);
    padding: 3px 8px;
    border-radius: 2px;
    font-family: var(--font-mono);
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.1s ease;
  }

  .tb-btn.small {
    padding: 2px 7px;
    font-size: 0.59rem;
  }

  .tb-btn:hover:not(:disabled) {
    color: var(--tx-bright);
    border-color: var(--bd-focus);
  }

  .tb-btn.on {
    color: var(--tx-bright);
    background: rgba(255, 255, 255, 0.07);
    border-color: var(--bd-active);
  }

  .tb-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .tb-sep {
    width: 1px;
    height: 12px;
    background: var(--bd-default);
    margin: 0 2px;
  }

  .tb-spacer { flex: 1; }

  .canvas-wrap {
    flex: 1;
    min-height: 320px;
    position: relative;
    background: #020207;
    cursor: grab;
    overflow: hidden;
    touch-action: none;
  }

  .canvas-wrap.dragging {
    cursor: grabbing;
  }

  .canvas-wrap canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
  }

  .ping-ring {
    position: absolute;
    inset: 0;
    pointer-events: none;
    border: 2px solid var(--info);
    border-radius: 2px;
    animation: pingRing 0.85s ease-out forwards;
  }

  .canvas-wrap.lock-busy::after {
    content: "";
    position: absolute;
    inset: 0;
    border: 2px solid rgba(var(--tier-accent-rgb), 0.5);
    border-radius: 2px;
    pointer-events: none;
    animation: pulse 0.7s ease-in-out infinite;
  }

  @media (max-width: 720px) {
    .canvas-wrap {
      min-height: 260px;
    }
  }
</style>
