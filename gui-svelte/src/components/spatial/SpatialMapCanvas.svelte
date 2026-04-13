<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from "svelte";
  import type { Vec3 } from "../helm/helmData.js";
  import type {
    SpatialLegendItem,
    SpatialLink,
    SpatialMapMode,
    SpatialRing,
    SpatialTrack,
  } from "./spatialMapTypes.js";

  const MIN_RADIUS = 250;
  const MAX_RADIUS = 5_000_000;
  const ELEVATION_STRIP_WIDTH = 110;

  type FocusMode = "free" | "ship" | "target" | "objective";
  type HitRecord = { id: string; x: number; y: number; distance: number };

  export let mode: SpatialMapMode = "tactical";
  export let tracks: SpatialTrack[] = [];
  export let rings: SpatialRing[] = [];
  export let links: SpatialLink[] = [];
  export let selectedId = "";
  export let ownshipId = "";
  export let objectiveId = "";
  export let initialRadius = 50_000;
  export let caption = "";
  export let legendItems: SpatialLegendItem[] = [];
  export let selectionActionLabel = "";
  export let selectionActionDisabled = false;

  const dispatch = createEventDispatcher<{
    select: { id: string };
    activate: { id: string };
  }>();

  let canvas: HTMLCanvasElement | null = null;
  let wrapper: HTMLDivElement | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let frameHandle = 0;
  let sciencePulseHandle: number | null = null;
  let redrawQueued = false;
  let initialized = false;

  let focusMode: FocusMode = "ship";
  let center: Vec3 = { x: 0, y: 0, z: 0 };
  let viewRadius = initialRadius;

  let dragging = false;
  let pointerDown = false;
  let dragDistance = 0;
  let dragStartX = 0;
  let dragStartY = 0;
  let originCenter = { x: 0, y: 0, z: 0 };
  let lastClickAt = 0;
  let lastClickId = "";
  let hitTargets: HitRecord[] = [];

  $: ownship = tracks.find((track) => track.id === ownshipId) ?? tracks.find((track) => track.kind === "ownship") ?? null;
  $: selectedTrack = tracks.find((track) => track.id === selectedId && track.selectable !== false) ?? null;
  $: objectiveTrack = tracks.find((track) => track.id === objectiveId) ?? null;
  $: selectableTracks = tracks.filter((track) => track.selectable !== false);
  $: activeFocusLabel = focusMode === "target"
    ? selectedTrack?.label ?? "Target"
    : focusMode === "objective"
      ? objectiveTrack?.label ?? "Objective"
      : focusMode === "ship"
        ? ownship?.label ?? "Own Ship"
        : "Free";
  $: scaleLabel = formatDistance(viewRadius * 2);

  $: if (!initialized && tracks.length > 0) {
    initializeCamera();
  }

  $: {
    mode;
    syncSciencePulse();
  }

  $: {
    mode;
    tracks;
    rings;
    links;
    selectedId;
    ownshipId;
    objectiveId;
    initialRadius;
    selectionActionLabel;
    selectionActionDisabled;
    focusMode;
    center.x;
    center.y;
    center.z;
    viewRadius;
    invalidateDraw();
  }

  onMount(() => {
    resizeObserver = new ResizeObserver(() => {
      invalidateDraw();
    });
    if (wrapper) resizeObserver.observe(wrapper);
    invalidateDraw();

    return () => {
      if (frameHandle) cancelAnimationFrame(frameHandle);
      if (sciencePulseHandle != null) window.clearInterval(sciencePulseHandle);
      sciencePulseHandle = null;
      redrawQueued = false;
      resizeObserver?.disconnect();
    };
  });

  onDestroy(() => {
    if (frameHandle) cancelAnimationFrame(frameHandle);
    if (sciencePulseHandle != null) window.clearInterval(sciencePulseHandle);
    sciencePulseHandle = null;
    redrawQueued = false;
    resizeObserver?.disconnect();
  });

  function initializeCamera() {
    initialized = true;
    focusMode = ownship ? "ship" : "free";
    viewRadius = normalizeRadius(initialRadius);
    if (ownship) {
      center = { ...ownship.position };
    } else if (tracks[0]) {
      center = { ...tracks[0].position };
    }
  }

  function normalizeRadius(radius: number): number {
    return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, Number.isFinite(radius) ? radius : initialRadius));
  }

  function formatDistance(value: number): string {
    if (!Number.isFinite(value)) return "--";
    const abs = Math.abs(value);
    if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)} Mm`;
    if (abs >= 1000) return `${(value / 1000).toFixed(abs >= 100_000 ? 0 : 1)} km`;
    return `${value.toFixed(abs >= 100 ? 0 : 1)} m`;
  }

  function getCanvasMetrics() {
    if (!wrapper || !canvas) return null;
    const rect = wrapper.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;

    const dpr = window.devicePixelRatio || 1;
    const width = rect.width;
    const height = rect.height;
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    const stripWidth = Math.min(ELEVATION_STRIP_WIDTH, Math.max(84, width * 0.18));
    return {
      dpr,
      width,
      height,
      mainWidth: Math.max(120, width - stripWidth),
      stripWidth,
    };
  }

  function pixelsPerMeter(mainWidth: number, height: number) {
    return Math.min(mainWidth, height) / (viewRadius * 2);
  }

  function syncFocus() {
    if (focusMode === "ship" && ownship) {
      updateCenterIfNeeded(ownship.position);
      return;
    }
    if (focusMode === "target" && selectedTrack) {
      updateCenterIfNeeded(selectedTrack.position);
      return;
    }
    if (focusMode === "objective" && objectiveTrack) {
      updateCenterIfNeeded(objectiveTrack.position);
    }
  }

  function updateCenterIfNeeded(next: Vec3) {
    if (
      Math.abs(center.x - next.x) < 0.01
      && Math.abs(center.y - next.y) < 0.01
      && Math.abs(center.z - next.z) < 0.01
    ) {
      return;
    }
    center = { ...next };
  }

  function toScreen(position: Vec3, mainWidth: number, height: number) {
    const ppm = pixelsPerMeter(mainWidth, height);
    return {
      x: mainWidth / 2 + (position.x - center.x) * ppm,
      y: height / 2 - (position.y - center.y) * ppm,
    };
  }

  function toElevation(position: Vec3, mainWidth: number, stripWidth: number, height: number) {
    const ppm = pixelsPerMeter(mainWidth, height);
    const baseX = mainWidth + stripWidth / 2;
    return {
      x: baseX,
      y: height / 2 - (position.z - center.z) * ppm,
      baseX,
    };
  }

  function screenToWorld(screenX: number, screenY: number, mainWidth: number, height: number) {
    const ppm = pixelsPerMeter(mainWidth, height);
    return {
      x: center.x + (screenX - mainWidth / 2) / ppm,
      y: center.y - (screenY - height / 2) / ppm,
    };
  }

  function draw(timestamp: number) {
    if (!canvas) return;
    const metrics = getCanvasMetrics();
    if (!metrics) return;
    syncFocus();

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.setTransform(metrics.dpr, 0, 0, metrics.dpr, 0, 0);
    ctx.clearRect(0, 0, metrics.width, metrics.height);

    hitTargets = [];

    drawBackground(ctx, metrics.width, metrics.height, metrics.mainWidth, metrics.stripWidth, timestamp);
    drawMainGrid(ctx, metrics.mainWidth, metrics.height);
    drawElevationGrid(ctx, metrics.mainWidth, metrics.stripWidth, metrics.height);
    drawLinks(ctx, metrics.mainWidth, metrics.height);
    drawRings(ctx, metrics.mainWidth, metrics.height);
    drawTracks(ctx, metrics.mainWidth, metrics.stripWidth, metrics.height, timestamp);
    drawOverlayLabels(ctx, metrics.width, metrics.height, metrics.mainWidth);
  }

  function invalidateDraw() {
    if (typeof window === "undefined" || redrawQueued) return;
    redrawQueued = true;
    frameHandle = requestAnimationFrame((timestamp) => {
      redrawQueued = false;
      draw(timestamp);
    });
  }

  function syncSciencePulse() {
    if (typeof window === "undefined") return;
    const needsPulse = mode === "science";
    if (needsPulse && sciencePulseHandle == null) {
      sciencePulseHandle = window.setInterval(() => invalidateDraw(), 260);
      return;
    }
    if (!needsPulse && sciencePulseHandle != null) {
      window.clearInterval(sciencePulseHandle);
      sciencePulseHandle = null;
    }
  }

  function drawBackground(
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number,
    mainWidth: number,
    stripWidth: number,
    timestamp: number,
  ) {
    const background = ctx.createLinearGradient(0, 0, width, height);
    if (mode === "science") {
      background.addColorStop(0, "#041019");
      background.addColorStop(1, "#081018");
    } else if (mode === "helm") {
      background.addColorStop(0, "#071018");
      background.addColorStop(1, "#0b1722");
    } else {
      background.addColorStop(0, "#091019");
      background.addColorStop(1, "#0f1622");
    }
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = "rgba(255,255,255,0.03)";
    ctx.fillRect(mainWidth, 0, stripWidth, height);

    if (mode === "science" && ownship) {
      const pulse = 0.45 + 0.25 * Math.sin(timestamp / 700);
      const mainPos = toScreen(ownship.position, mainWidth, height);
      [0.28, 0.52, 0.76].forEach((ratio, index) => {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(68, 221, 255, ${0.06 + pulse * 0.08})`;
        ctx.lineWidth = 1;
        ctx.arc(mainPos.x, mainPos.y, ratio * Math.min(mainWidth, height) * (0.55 + index * 0.1), 0, Math.PI * 2);
        ctx.stroke();
      });
    }
  }

  function drawMainGrid(ctx: CanvasRenderingContext2D, mainWidth: number, height: number) {
    const step = Math.max(36, Math.min(mainWidth, height) / 6);
    ctx.strokeStyle = "rgba(170, 205, 255, 0.08)";
    ctx.lineWidth = 1;

    for (let x = step; x < mainWidth; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = step; y < height; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(mainWidth, y);
      ctx.stroke();
    }

    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.beginPath();
    ctx.moveTo(mainWidth / 2, 0);
    ctx.lineTo(mainWidth / 2, height);
    ctx.moveTo(0, height / 2);
    ctx.lineTo(mainWidth, height / 2);
    ctx.stroke();
  }

  function drawElevationGrid(ctx: CanvasRenderingContext2D, mainWidth: number, stripWidth: number, height: number) {
    const left = mainWidth;
    const centerX = left + stripWidth / 2;

    ctx.strokeStyle = "rgba(255,255,255,0.14)";
    ctx.beginPath();
    ctx.moveTo(centerX, 0);
    ctx.lineTo(centerX, height);
    ctx.stroke();

    const step = Math.max(40, height / 6);
    ctx.strokeStyle = "rgba(170, 205, 255, 0.08)";
    for (let y = step; y < height; y += step) {
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(left + stripWidth, y);
      ctx.stroke();
    }
  }

  function drawLinks(ctx: CanvasRenderingContext2D, mainWidth: number, height: number) {
    for (const link of links) {
      const from = toScreen(link.from, mainWidth, height);
      const to = toScreen(link.to, mainWidth, height);
      ctx.save();
      ctx.strokeStyle = link.color;
      ctx.lineWidth = link.faint ? 1 : 1.5;
      ctx.setLineDash(link.dashed ? [7, 5] : []);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();

      if (link.arrow) {
        drawArrowHead(ctx, from.x, from.y, to.x, to.y, link.color, link.faint ? 1 : 1.5);
      }
      ctx.restore();

      if (link.label) {
        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2;
        ctx.fillStyle = "rgba(230,240,255,0.85)";
        ctx.font = "10px JetBrains Mono";
        ctx.fillText(link.label, midX + 6, midY - 6);
      }
    }
  }

  function drawRings(ctx: CanvasRenderingContext2D, mainWidth: number, height: number) {
    const ppm = pixelsPerMeter(mainWidth, height);
    for (const ring of rings) {
      const centerPos = toScreen(ring.center ?? center, mainWidth, height);
      ctx.save();
      ctx.strokeStyle = ring.color;
      ctx.lineWidth = 1;
      ctx.setLineDash(ring.dashed ? [8, 6] : []);
      ctx.beginPath();
      ctx.arc(centerPos.x, centerPos.y, ring.radius * ppm, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      if (ring.label) {
        ctx.fillStyle = ring.color;
        ctx.font = "10px JetBrains Mono";
        ctx.fillText(ring.label, centerPos.x + ring.radius * ppm + 6, centerPos.y - 6);
      }
    }
  }

  function drawTracks(
    ctx: CanvasRenderingContext2D,
    mainWidth: number,
    stripWidth: number,
    height: number,
    timestamp: number,
  ) {
    const ppm = pixelsPerMeter(mainWidth, height);

    for (const track of tracks) {
      const mainPos = toScreen(track.position, mainWidth, height);
      const stripPos = toElevation(track.position, mainWidth, stripWidth, height);

      if (track.selectable !== false) {
        hitTargets.push({ id: track.id, x: mainPos.x, y: mainPos.y, distance: 14 });
        hitTargets.push({ id: track.id, x: stripPos.x, y: stripPos.y, distance: 14 });
      }

      drawMainTrack(ctx, track, mainPos.x, mainPos.y, ppm, timestamp);
      drawElevationTrack(ctx, track, stripPos.x, stripPos.y, mainWidth, stripWidth, height);
    }
  }

  function drawMainTrack(
    ctx: CanvasRenderingContext2D,
    track: SpatialTrack,
    x: number,
    y: number,
    ppm: number,
    timestamp: number,
  ) {
    const selected = track.id === selectedId;
    const palette = colorForTrack(track);
    const haloAlpha = selected ? 0.32 : track.kind === "ghost" ? 0.18 : 0.1;

    if ((track.confidence ?? 1) < 0.96 || track.kind === "ghost") {
      const confidence = Math.max(0.08, track.confidence ?? 0.35);
      ctx.save();
      ctx.strokeStyle = `rgba(${palette.rgb}, ${0.16 + (1 - confidence) * 0.22})`;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 5]);
      ctx.beginPath();
      ctx.ellipse(
        x,
        y,
        12 + (1 - confidence) * 22,
        8 + (1 - confidence) * 14,
        timestamp / 1800,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
      ctx.restore();
    }

    if (track.kind === "munition" || track.kind === "projectile") {
      const velocity = track.velocity ?? { x: 0, y: 0, z: 0 };
      ctx.save();
      ctx.strokeStyle = `rgba(${palette.rgb}, 0.55)`;
      ctx.lineWidth = track.kind === "munition" ? 2 : 1.4;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + velocity.x * ppm * 0.4, y - velocity.y * ppm * 0.4);
      ctx.stroke();
      ctx.restore();
    }

    if (track.velocity && track.kind !== "projectile") {
      const vectorScale = track.kind === "ownship" && mode === "helm" ? 0.5 : 0.28;
      const vectorWidth = track.kind === "ownship" && mode === "helm" ? 1.8 : 1;
      ctx.save();
      ctx.strokeStyle = `rgba(${palette.rgb}, ${track.kind === "ownship" && mode === "helm" ? 0.6 : 0.38})`;
      ctx.lineWidth = vectorWidth;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + track.velocity.x * ppm * vectorScale, y - track.velocity.y * ppm * vectorScale);
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.fillStyle = `rgba(${palette.rgb}, ${0.14 + haloAlpha})`;
    ctx.beginPath();
    ctx.arc(x, y, selected ? 14 : track.kind === "ownship" ? 11 : 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    drawTrackSymbol(ctx, track, x, y, palette.color, selected);

    ctx.fillStyle = selected ? "#f4fbff" : "rgba(235,243,255,0.88)";
    ctx.font = selected ? "700 11px JetBrains Mono" : "10px JetBrains Mono";
    ctx.fillText(track.label, x + 10, y - 8);
    if (track.annotation) {
      ctx.fillStyle = "rgba(190,208,230,0.85)";
      ctx.font = "10px JetBrains Mono";
      ctx.fillText(track.annotation, x + 10, y + 10);
    }
  }

  function drawTrackSymbol(
    ctx: CanvasRenderingContext2D,
    track: SpatialTrack,
    x: number,
    y: number,
    color: string,
    selected: boolean,
  ) {
    const size = selected ? 8 : 6;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = selected ? 2 : 1.4;

    switch (track.kind) {
      case "ownship":
      case "friendly": {
        const heading = ((track.headingDeg ?? 0) - 90) * (Math.PI / 180);
        ctx.translate(x, y);
        ctx.rotate(heading);
        ctx.beginPath();
        ctx.moveTo(0, -size - 1);
        ctx.lineTo(size * 0.8, size);
        ctx.lineTo(0, size * 0.45);
        ctx.lineTo(-size * 0.8, size);
        ctx.closePath();
        ctx.fill();
        break;
      }
      case "hostile":
      case "munition": {
        ctx.beginPath();
        ctx.moveTo(x, y - size);
        ctx.lineTo(x + size, y);
        ctx.lineTo(x, y + size);
        ctx.lineTo(x - size, y);
        ctx.closePath();
        track.kind === "munition" ? ctx.stroke() : ctx.fill();
        break;
      }
      case "waypoint":
      case "beacon":
      case "objective": {
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - size - 3, y);
        ctx.lineTo(x + size + 3, y);
        ctx.moveTo(x, y - size - 3);
        ctx.lineTo(x, y + size + 3);
        ctx.stroke();
        break;
      }
      case "ghost": {
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.stroke();
        break;
      }
      case "projectile": {
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fill();
        break;
      }
      default: {
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.restore();
  }

  function drawElevationTrack(
    ctx: CanvasRenderingContext2D,
    track: SpatialTrack,
    x: number,
    y: number,
    mainWidth: number,
    stripWidth: number,
    height: number,
  ) {
    const palette = colorForTrack(track);
    const selected = track.id === selectedId;
    const left = mainWidth;
    const right = left + stripWidth;
    const stalkFrom = toScreen(track.position, mainWidth, height);
    const showConnector = shouldDrawElevationConnector(track, selected);
    const showLabel = showConnector || Boolean(track.elevationLabel) || track.emphasis || track.kind === "ownship";

    if (showConnector) {
      ctx.save();
      ctx.strokeStyle = `rgba(${palette.rgb}, ${selected ? 0.42 : 0.24})`;
      ctx.lineWidth = selected ? 1.2 : 1;
      ctx.setLineDash(track.kind === "ghost" ? [4, 4] : []);
      ctx.beginPath();
      ctx.moveTo(stalkFrom.x, stalkFrom.y);
      ctx.lineTo(x, y);
      ctx.stroke();
      ctx.restore();
    }

    ctx.fillStyle = palette.color;
    ctx.beginPath();
    ctx.arc(x, y, selected ? 6 : 4, 0, Math.PI * 2);
    ctx.fill();

    if (showLabel) {
      ctx.fillStyle = "rgba(220,230,245,0.85)";
      ctx.font = selected ? "700 10px JetBrains Mono" : "10px JetBrains Mono";
      ctx.fillText(track.elevationLabel ?? track.label, left + 8, y - 6);
      ctx.fillText(formatDistance(track.position.z), left + 8, y + 9);
    }

    ctx.strokeStyle = `rgba(${palette.rgb}, ${showConnector || selected ? 0.18 : 0.08})`;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  function drawOverlayLabels(ctx: CanvasRenderingContext2D, width: number, height: number, mainWidth: number) {
    ctx.fillStyle = "rgba(180, 200, 222, 0.8)";
    ctx.font = "10px JetBrains Mono";
    ctx.fillText("Plan view", 10, 16);
    ctx.fillText("Elevation", mainWidth + 8, 16);
    ctx.fillText(`Focus: ${activeFocusLabel}`, 10, height - 10);
    ctx.fillText(`Span: ${scaleLabel}`, width - 110, height - 10);
  }

  function shouldDrawElevationConnector(track: SpatialTrack, selected: boolean) {
    switch (track.elevationConnector ?? "auto") {
      case "always":
        return true;
      case "selected":
        return selected;
      case "none":
        return false;
      default:
        return selected || track.kind === "ownship" || track.kind === "objective" || track.kind === "waypoint" || track.emphasis;
    }
  }

  function drawArrowHead(
    ctx: CanvasRenderingContext2D,
    fromX: number,
    fromY: number,
    toX: number,
    toY: number,
    color: string,
    width: number,
  ) {
    const angle = Math.atan2(toY - fromY, toX - fromX);
    const length = 8;
    ctx.save();
    ctx.fillStyle = color;
    ctx.translate(toX, toY);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-length, 4 + width);
    ctx.lineTo(-length, -4 - width);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function colorForTrack(track: SpatialTrack) {
    switch (track.kind) {
      case "ownship":
        return { color: "#8ef7ff", rgb: "142, 247, 255" };
      case "friendly":
        return { color: "#00ff88", rgb: "0, 255, 136" };
      case "hostile":
        return { color: "#ff5a5a", rgb: "255, 90, 90" };
      case "waypoint":
      case "beacon":
      case "objective":
        return { color: "#ffd46b", rgb: "255, 212, 107" };
      case "ghost":
        return { color: "#61d8ff", rgb: "97, 216, 255" };
      case "projectile":
        return { color: "#f9f871", rgb: "249, 248, 113" };
      case "munition":
        return { color: "#ff9966", rgb: "255, 153, 102" };
      default:
        return { color: "#82b8ff", rgb: "130, 184, 255" };
    }
  }

  function setFocus(nextFocus: FocusMode) {
    focusMode = nextFocus;
    syncFocus();
    invalidateDraw();
  }

  function fitAll() {
    const points = tracks
      .filter((track) => track.kind !== "projectile")
      .map((track) => track.position);
    if (points.length === 0) return;

    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const zs = points.map((point) => point.z);
    center = {
      x: (Math.min(...xs) + Math.max(...xs)) / 2,
      y: (Math.min(...ys) + Math.max(...ys)) / 2,
      z: (Math.min(...zs) + Math.max(...zs)) / 2,
    };

    const xSpan = Math.max(...xs) - Math.min(...xs);
    const ySpan = Math.max(...ys) - Math.min(...ys);
    const zSpan = Math.max(...zs) - Math.min(...zs);
    viewRadius = normalizeRadius(Math.max(xSpan, ySpan, zSpan) * 0.65 + 2000);
    focusMode = "free";
    invalidateDraw();
  }

  function resetView() {
    viewRadius = normalizeRadius(initialRadius);
    focusMode = ownship ? "ship" : "free";
    syncFocus();
    invalidateDraw();
  }

  function zoomBy(factor: number, clientX?: number, clientY?: number) {
    const metrics = getCanvasMetrics();
    if (!metrics) return;

    const nextRadius = normalizeRadius(viewRadius * factor);
    if (clientX == null || clientY == null) {
      viewRadius = nextRadius;
      invalidateDraw();
      return;
    }

    const rect = canvas?.getBoundingClientRect();
    if (!rect) {
      viewRadius = nextRadius;
      invalidateDraw();
      return;
    }

    const localX = ((clientX - rect.left) / rect.width) * metrics.width;
    const localY = ((clientY - rect.top) / rect.height) * metrics.height;
    if (localX > metrics.mainWidth) {
      viewRadius = nextRadius;
      invalidateDraw();
      return;
    }

    const before = screenToWorld(localX, localY, metrics.mainWidth, metrics.height);
    viewRadius = nextRadius;
    const after = screenToWorld(localX, localY, metrics.mainWidth, metrics.height);
    center = {
      ...center,
      x: center.x + (before.x - after.x),
      y: center.y + (before.y - after.y),
    };
    focusMode = "free";
    invalidateDraw();
  }

  function findNearestHit(clientX: number, clientY: number) {
    const rect = canvas?.getBoundingClientRect();
    if (!rect) return null;
    const metrics = getCanvasMetrics();
    if (!metrics) return null;
    const x = ((clientX - rect.left) / rect.width) * metrics.width;
    const y = ((clientY - rect.top) / rect.height) * metrics.height;

    let best: HitRecord | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const hit of hitTargets) {
      const distance = Math.hypot(hit.x - x, hit.y - y);
      if (distance < hit.distance && distance < bestDistance) {
        best = hit;
        bestDistance = distance;
      }
    }
    return best;
  }

  function handlePointerDown(event: PointerEvent) {
    if (!canvas) return;
    pointerDown = true;
    dragging = false;
    dragDistance = 0;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    originCenter = { ...center };
    canvas.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent) {
    if (!pointerDown || !canvas) return;
    const metrics = getCanvasMetrics();
    if (!metrics) return;
    const ppm = pixelsPerMeter(metrics.mainWidth, metrics.height);
    const deltaX = event.clientX - dragStartX;
    const deltaY = event.clientY - dragStartY;
    dragDistance = Math.max(dragDistance, Math.hypot(deltaX, deltaY));
    if (dragDistance < 3) return;
    dragging = true;
    focusMode = "free";
    center = {
      ...center,
      x: originCenter.x - deltaX / ppm,
      y: originCenter.y + deltaY / ppm,
    };
    invalidateDraw();
  }

  function handlePointerUp(event: PointerEvent) {
    if (!canvas) return;
    if (canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }

    if (!dragging && dragDistance < 6) {
      const hit = findNearestHit(event.clientX, event.clientY);
      if (hit) {
        dispatch("select", { id: hit.id });
        const now = performance.now();
        if (lastClickId === hit.id && now - lastClickAt < 350) {
          dispatch("activate", { id: hit.id });
        }
        lastClickId = hit.id;
        lastClickAt = now;
      }
    }

    pointerDown = false;
    dragging = false;
  }

  function handleWheel(event: WheelEvent) {
    event.preventDefault();
    zoomBy(event.deltaY > 0 ? 1.18 : 0.84, event.clientX, event.clientY);
  }
</script>

<div class="map-shell">
  <div class="toolbar">
    <div class="summary">
      <strong>{mode.toUpperCase()}</strong>
      <span>{tracks.filter((track) => track.kind !== "projectile" && track.kind !== "munition").length} tracks</span>
      <span>Focus {activeFocusLabel}</span>
    </div>

    <div class="controls">
      <button type="button" class:active={focusMode === "ship"} disabled={!ownship} on:click={() => setFocus("ship")}>Ship</button>
      <button type="button" class:active={focusMode === "target"} disabled={!selectedTrack} on:click={() => setFocus("target")}>Target</button>
      <button type="button" class:active={focusMode === "objective"} disabled={!objectiveTrack} on:click={() => setFocus("objective")}>Objective</button>
      <button type="button" on:click={fitAll}>Fit All</button>
      <button type="button" on:click={resetView}>Reset</button>
      <button type="button" on:click={() => zoomBy(1.18)}>-</button>
      <button type="button" on:click={() => zoomBy(0.84)}>+</button>
      <slot name="actions" />
    </div>
  </div>

  <div class="canvas-wrap" bind:this={wrapper}>
    <canvas
      bind:this={canvas}
      on:pointerdown={handlePointerDown}
      on:pointermove={handlePointerMove}
      on:pointerup={handlePointerUp}
      on:pointercancel={handlePointerUp}
      on:wheel={handleWheel}
    ></canvas>

    <div class="overlay-top">
      <div class="scale-chip">Span {scaleLabel}</div>
      {#if selectedTrack}
        <div class="selection-chip">
          <span>{selectedTrack.label}</span>
          {#if selectedTrack.annotation}<span>{selectedTrack.annotation}</span>{/if}
          {#if selectionActionLabel}
            <button type="button" disabled={selectionActionDisabled} on:click={() => dispatch("activate", { id: selectedTrack.id })}>
              {selectionActionLabel}
            </button>
          {/if}
        </div>
      {/if}
    </div>

    {#if legendItems.length > 0}
      <div class="legend">
        {#each legendItems as item}
          <span class="legend-item">
            <span class="swatch" style="--swatch: {item.color}"></span>
            <span>{item.symbol ? `${item.symbol} ` : ""}{item.label}</span>
          </span>
        {/each}
      </div>
    {/if}
  </div>

  {#if caption}
    <div class="caption">{caption}</div>
  {/if}
</div>

<style>
  .map-shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
    min-width: 0;
  }

  .toolbar,
  .summary,
  .controls,
  .overlay-top,
  .legend {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    flex-wrap: wrap;
  }

  .toolbar {
    justify-content: space-between;
  }

  .summary {
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .summary strong {
    color: var(--text-primary);
    font-family: var(--font-mono);
  }

  .controls {
    justify-content: flex-end;
  }

  .controls button,
  .selection-chip button {
    min-height: unset;
    padding: 7px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
  }

  .controls button.active {
    border-color: var(--tier-accent, var(--hud-primary));
    background: rgba(var(--tier-accent-rgb, 104, 179, 255), 0.18);
    color: var(--text-primary);
  }

  .controls button:disabled,
  .selection-chip button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .canvas-wrap {
    position: relative;
    min-height: clamp(300px, 42vh, 560px);
    height: clamp(320px, 46vh, 620px);
    border-radius: var(--radius-sm);
    overflow: hidden;
    border: 1px solid var(--border-subtle);
    background: #081019;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
    cursor: grab;
    touch-action: none;
  }

  canvas:active {
    cursor: grabbing;
  }

  .overlay-top {
    position: absolute;
    left: 10px;
    top: 10px;
    right: 10px;
    justify-content: space-between;
    pointer-events: none;
  }

  .scale-chip,
  .selection-chip,
  .legend {
    background: rgba(4, 7, 12, 0.82);
    border: 1px solid rgba(180, 205, 255, 0.16);
    border-radius: 999px;
    padding: 6px 10px;
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .selection-chip {
    pointer-events: auto;
  }

  .selection-chip span {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .legend {
    position: absolute;
    left: 10px;
    bottom: 10px;
    gap: 10px;
    flex-wrap: wrap;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .swatch {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--swatch);
    box-shadow: 0 0 10px color-mix(in srgb, var(--swatch) 55%, transparent);
  }

  .caption {
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
  }

  @media (max-width: 760px) {
    .canvas-wrap {
      min-height: clamp(260px, 48vh, 420px);
      height: clamp(280px, 50vh, 460px);
    }

    .toolbar {
      align-items: flex-start;
    }

    .controls {
      justify-content: flex-start;
    }

    .overlay-top {
      gap: 8px;
      align-items: flex-start;
    }

    .selection-chip {
      max-width: 100%;
      border-radius: var(--radius-sm);
    }

    .legend {
      right: 10px;
      border-radius: var(--radius-sm);
    }
  }
</style>
