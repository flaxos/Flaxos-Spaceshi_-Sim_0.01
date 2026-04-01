/**
 * Tactical Map Component
 * Primary combat display: 2D plot of sensor contacts, trajectory projection,
 * weapon engagement envelopes, firing solution confidence cones, projectile
 * tracks, error ellipses, and classification labels.
 *
 * All displayed information is limited by what own sensors can detect —
 * contacts outside sensor range don't appear (server-enforced).
 * Uncertain contacts show error ellipses reflecting track quality.
 */

import { stateManager } from "../js/state-manager.js";

const MAP_SCALE_OPTIONS = [1000, 5000, 10000, 50000, 100000, 250000, 500000, 1000000]; // meters per screen radius

const WEAPON_RANGES = {
  PDC: 5000,        // 5km in meters
  RAILGUN: 500000,  // 500km in meters
};

// Trajectory projection: how many seconds ahead to draw
const TRAJECTORY_SECONDS = 60;
const TRAJECTORY_STEPS = 20;

class TacticalMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._scaleIndex = 2; // Default 10km
    this._autoFit = true; // Auto-scale to fit all contacts
    this._showVelocityVectors = true;
    this._showHeading = true;
    this._showGrid = true;
    this._showWeaponArcs = false;
    this._showTrajectory = true;
    this._showSolutions = true;
    this._selectedContact = null;
    this._canvas = null;
    this._ctx = null;
    // Track screen positions for click detection (separate from frozen state)
    this._contactScreenPositions = new Map();

    // Kill confirmation: track contacts from previous frame to detect disappearances
    this._previousContactIds = new Set();
    // Last known world positions for contacts (for explosion placement)
    this._lastContactPositions = new Map();
    // Active explosion effects: {position: {x,z}, startTime, duration}
    this._explosions = [];
  }

  connectedCallback() {
    this.render();
    this._setupCanvas();
    this._subscribe();
    this._setupInteraction();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._draw();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
        }

        .map-controls {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          background: rgba(0, 0, 0, 0.2);
          flex-wrap: wrap;
        }

        .control-group {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .control-label {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
          text-transform: uppercase;
        }

        .control-btn {
          background: transparent;
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-secondary, #888899);
          padding: 4px 8px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.7rem;
          min-height: auto;
          min-width: 28px;
        }

        .control-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary, #e0e0e0);
        }

        .control-btn.active {
          background: var(--status-info, #00aaff);
          color: #000;
          border-color: var(--status-info, #00aaff);
        }

        .scale-display {
          color: var(--text-primary, #e0e0e0);
          min-width: 60px;
          text-align: center;
        }

        .map-container {
          flex: 1;
          position: relative;
          background: var(--bg-input, #0d0d12);
          overflow: hidden;
        }

        canvas {
          width: 100%;
          height: 100%;
          display: block;
        }

        .legend {
          position: absolute;
          bottom: 8px;
          left: 8px;
          background: rgba(0, 0, 0, 0.7);
          padding: 8px;
          border-radius: 4px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .legend-item {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
        }

        .legend-item:last-child {
          margin-bottom: 0;
        }

        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .legend-dot.player { background: #00aaff; }
        .legend-dot.friendly { background: #00ff88; }
        .legend-dot.hostile { background: #ff4444; }
        .legend-dot.neutral { background: #888899; }
        .legend-dot.unknown { background: #ffaa00; }

        .contact-info {
          position: absolute;
          top: 8px;
          right: 8px;
          background: rgba(0, 0, 0, 0.8);
          padding: 12px;
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
          min-width: 150px;
          display: none;
        }

        .contact-info.visible {
          display: block;
        }

        .contact-info-title {
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .contact-info-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
          font-size: 0.7rem;
        }

        .contact-info-label {
          color: var(--text-dim, #555566);
        }

        .contact-info-value {
          color: var(--text-primary, #e0e0e0);
        }
      </style>

      <div class="map-controls">
        <div class="control-group">
          <span class="control-label">Scale</span>
          <button class="control-btn" id="zoom-out">−</button>
          <span class="scale-display" id="scale-display">10 km</span>
          <button class="control-btn" id="zoom-in">+</button>
          <button class="control-btn active" id="auto-fit" title="Auto-fit to show all contacts">A</button>
        </div>
        <div class="control-group">
          <button class="control-btn" id="toggle-vectors" title="Velocity Vectors">V</button>
          <button class="control-btn" id="toggle-heading" title="Heading Indicator">H</button>
          <button class="control-btn" id="toggle-grid" title="Grid">G</button>
          <button class="control-btn" id="toggle-weapon-arcs" title="Weapon Envelopes">W</button>
          <button class="control-btn" id="toggle-trajectory" title="Trajectory Projection">T</button>
          <button class="control-btn" id="toggle-solutions" title="Firing Solutions">S</button>
        </div>
      </div>

      <div class="map-container" id="map-container">
        <canvas id="tactical-canvas"></canvas>

        <div class="legend">
          <div class="legend-item">
            <span class="legend-dot player"></span>
            <span>Player</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot friendly"></span>
            <span>Friendly</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot hostile"></span>
            <span>Hostile</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot neutral"></span>
            <span>Neutral</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot unknown"></span>
            <span>Unknown</span>
          </div>
        </div>

        <div class="contact-info" id="contact-info">
          <div class="contact-info-title" id="contact-name">---</div>
          <div class="contact-info-row">
            <span class="contact-info-label">Type:</span>
            <span class="contact-info-value" id="contact-type">---</span>
          </div>
          <div class="contact-info-row">
            <span class="contact-info-label">Distance:</span>
            <span class="contact-info-value" id="contact-distance">---</span>
          </div>
          <div class="contact-info-row">
            <span class="contact-info-label">Bearing:</span>
            <span class="contact-info-value" id="contact-bearing">---</span>
          </div>
          <div class="contact-info-row">
            <span class="contact-info-label">Velocity:</span>
            <span class="contact-info-value" id="contact-velocity">---</span>
          </div>
          <div class="contact-info-row">
            <span class="contact-info-label">Confidence:</span>
            <span class="contact-info-value" id="contact-confidence">---</span>
          </div>
          <div class="contact-info-row">
            <span class="contact-info-label">Method:</span>
            <span class="contact-info-value" id="contact-method">---</span>
          </div>
        </div>
      </div>
    `;
  }

  _setupCanvas() {
    this._canvas = this.shadowRoot.getElementById("tactical-canvas");
    this._ctx = this._canvas.getContext("2d");

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      this._resizeCanvas();
      this._draw();
    });
    resizeObserver.observe(this.shadowRoot.getElementById("map-container"));

    this._resizeCanvas();
  }

  _resizeCanvas() {
    const container = this.shadowRoot.getElementById("map-container");
    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    this._canvas.width = rect.width * dpr;
    this._canvas.height = rect.height * dpr;
    this._ctx.scale(dpr, dpr);

    this._canvasWidth = rect.width;
    this._canvasHeight = rect.height;
  }

  _setupInteraction() {
    // Zoom controls — manual zoom disables auto-fit
    this.shadowRoot.getElementById("zoom-in").addEventListener("click", () => {
      if (this._scaleIndex > 0) {
        this._scaleIndex--;
        this._setAutoFit(false);
        this._updateScaleDisplay();
        this._draw();
      }
    });

    this.shadowRoot.getElementById("zoom-out").addEventListener("click", () => {
      if (this._scaleIndex < MAP_SCALE_OPTIONS.length - 1) {
        this._scaleIndex++;
        this._setAutoFit(false);
        this._updateScaleDisplay();
        this._draw();
      }
    });

    // Auto-fit toggle
    const autoFitBtn = this.shadowRoot.getElementById("auto-fit");
    autoFitBtn.addEventListener("click", () => {
      this._setAutoFit(!this._autoFit);
      this._draw();
    });

    // Toggle buttons
    const toggles = [
      { id: "toggle-vectors", prop: "_showVelocityVectors" },
      { id: "toggle-heading", prop: "_showHeading" },
      { id: "toggle-grid", prop: "_showGrid" },
      { id: "toggle-weapon-arcs", prop: "_showWeaponArcs" },
      { id: "toggle-trajectory", prop: "_showTrajectory" },
      { id: "toggle-solutions", prop: "_showSolutions" },
    ];

    for (const { id, prop } of toggles) {
      const btn = this.shadowRoot.getElementById(id);
      if (this[prop]) btn.classList.add("active");
      btn.addEventListener("click", () => {
        this[prop] = !this[prop];
        btn.classList.toggle("active", this[prop]);
        this._draw();
      });
    }

    // Canvas click for contact selection
    this._canvas.addEventListener("click", (e) => {
      this._handleCanvasClick(e);
    });

    this._updateScaleDisplay();
  }

  _setAutoFit(enabled) {
    this._autoFit = enabled;
    const btn = this.shadowRoot.getElementById("auto-fit");
    if (btn) btn.classList.toggle("active", enabled);
  }

  /**
   * Resolve a contact's world position. Prefers the position field from telemetry,
   * but reconstructs from distance + bearing relative to the player if missing.
   */
  _resolveContactPosition(contact, playerPos) {
    // If telemetry includes the actual position, use it directly
    if (contact.position && (contact.position.x !== undefined || contact.position.y !== undefined)) {
      return contact.position;
    }

    // Reconstruct from distance + bearing.
    // Server bearing is {yaw, pitch} where yaw = atan2(dy, dx) in the XY plane.
    // A scalar bearing is treated as yaw in degrees.
    if (contact.distance != null && contact.bearing != null) {
      const yawDeg = typeof contact.bearing === "object"
        ? (contact.bearing.yaw || 0)
        : contact.bearing;
      const pitchDeg = typeof contact.bearing === "object"
        ? (contact.bearing.pitch || 0)
        : 0;
      const yawRad = (yawDeg * Math.PI) / 180;
      const pitchRad = (pitchDeg * Math.PI) / 180;
      const horizDist = contact.distance * Math.cos(pitchRad);
      return {
        x: playerPos.x + horizDist * Math.cos(yawRad),
        y: playerPos.y + horizDist * Math.sin(yawRad),
        z: playerPos.z + contact.distance * Math.sin(pitchRad),
      };
    }

    // No usable position data — place at player origin (will overlap)
    return { x: playerPos.x, y: playerPos.y, z: playerPos.z };
  }

  /**
   * Auto-fit the scale so all contacts are visible with some padding.
   */
  _autoFitScale(contacts, playerPos) {
    if (!contacts || contacts.length === 0) return;

    let maxDist = 0;
    for (const contact of contacts) {
      const pos = this._resolveContactPosition(contact, playerPos);
      const dx = pos.x - playerPos.x;
      const dz = pos.z - playerPos.z;
      const dist = Math.sqrt(dx * dx + dz * dz);
      if (dist > maxDist) maxDist = dist;
    }

    if (maxDist < 100) return; // All contacts very close, keep current scale

    // Add 20% padding so contacts aren't at the very edge
    const neededScale = maxDist * 1.2;

    // Find the smallest scale option that fits
    for (let i = 0; i < MAP_SCALE_OPTIONS.length; i++) {
      if (MAP_SCALE_OPTIONS[i] >= neededScale) {
        this._scaleIndex = i;
        this._updateScaleDisplay();
        return;
      }
    }

    // If nothing fits, use the largest available
    this._scaleIndex = MAP_SCALE_OPTIONS.length - 1;
    this._updateScaleDisplay();
  }

  _updateScaleDisplay() {
    const scale = MAP_SCALE_OPTIONS[this._scaleIndex];
    let displayText;
    if (scale >= 1000) {
      displayText = `${scale / 1000} km`;
    } else {
      displayText = `${scale} m`;
    }
    this.shadowRoot.getElementById("scale-display").textContent = displayText;
  }

  _draw() {
    if (!this._ctx || !this._canvasWidth) return;

    const ctx = this._ctx;
    const w = this._canvasWidth;
    const h = this._canvasHeight;
    const centerX = w / 2;
    const centerY = h / 2;
    const scale = MAP_SCALE_OPTIONS[this._scaleIndex];
    const pixelsPerMeter = Math.min(w, h) / 2 / scale;

    // Clear
    ctx.fillStyle = "#050508"; // deep void
    ctx.fillRect(0, 0, w, h);

    // Vignette: darker at edges, slightly lighter at center
    const vignette = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(w, h) * 0.7);
    vignette.addColorStop(0, "rgba(20, 20, 30, 0.15)");
    vignette.addColorStop(1, "rgba(0, 0, 0, 0.6)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, w, h);

    // Get player ship state
    const ship = stateManager.getShipState();
    const playerPos = ship?.position || { x: 0, y: 0, z: 0 };
    const playerVel = ship?.velocity || { x: 0, y: 0, z: 0 };
    const playerHeading = ship?.orientation?.yaw || 0;

    // Draw grid
    if (this._showGrid) {
      this._drawGrid(ctx, w, h, centerX, centerY, scale, pixelsPerMeter);
    }

    // Draw range rings
    this._drawRangeRings(ctx, centerX, centerY, scale, pixelsPerMeter);

    // Draw environment: asteroid fields, hazard zones (behind everything else)
    this._drawEnvironment(ctx, playerPos, centerX, centerY, pixelsPerMeter);

    // Draw weapon engagement envelopes (before contacts so blips draw on top)
    if (this._showWeaponArcs) {
      this._drawWeaponArcs(ctx, centerX, centerY, scale, pixelsPerMeter);
    }

    // Draw own ship trajectory projection
    if (this._showTrajectory) {
      this._drawTrajectoryProjection(ctx, centerX, centerY, playerVel, pixelsPerMeter, scale);
    }

    // Draw contacts
    const contacts = stateManager.getContacts() || [];

    // Kill confirmation: detect contacts that disappeared since last frame.
    // A contact that was tracked last frame but is now absent likely got destroyed.
    const currentContactIds = new Set(contacts.map(c => c.id || c.contact_id));
    for (const prevId of this._previousContactIds) {
      if (!currentContactIds.has(prevId)) {
        const lastPos = this._lastContactPositions.get(prevId);
        if (lastPos) {
          this._explosions.push({
            position: { x: lastPos.x, z: lastPos.z },
            startTime: performance.now(),
            duration: 2000, // 2 seconds
          });
        }
      }
    }
    this._previousContactIds = currentContactIds;

    // Update last known positions for all current contacts
    for (const contact of contacts) {
      const pos = this._resolveContactPosition(contact, playerPos);
      this._lastContactPositions.set(contact.id || contact.contact_id, { x: pos.x, z: pos.z });
    }
    // Clean up stale position entries for contacts gone for more than 10 seconds
    for (const [id] of this._lastContactPositions) {
      if (!currentContactIds.has(id)) {
        // Keep for a bit so explosions can still reference it, then clean
        // (the explosion already captured the position, so this is just housekeeping)
        this._lastContactPositions.delete(id);
      }
    }

    // Auto-fit scale to show all contacts before rendering.
    if (this._autoFit && contacts.length > 0) {
      const prevIndex = this._scaleIndex;
      this._autoFitScale(contacts, playerPos);
      if (this._scaleIndex !== prevIndex) {
        this._draw();
        return;
      }
    }

    // Draw firing solution confidence cones (behind contacts)
    if (this._showSolutions) {
      this._drawFiringSolutions(ctx, centerX, centerY, playerPos, contacts, pixelsPerMeter, scale);
    }

    // Clear screen position tracking for this frame
    this._contactScreenPositions.clear();

    contacts.forEach(contact => {
      this._drawContact(ctx, contact, playerPos, centerX, centerY, pixelsPerMeter, playerVel, scale);
    });

    // Draw projectile tracks
    this._drawProjectiles(ctx, playerPos, centerX, centerY, pixelsPerMeter);

    // Draw torpedo tracks (separate from projectiles — torpedoes are guided,
    // larger, and need distinct rendering with state/target indicators)
    this._drawTorpedoes(ctx, playerPos, centerX, centerY, pixelsPerMeter);

    // Draw kill confirmation explosions (on top of everything else)
    this._drawExplosions(ctx, playerPos, centerX, centerY, pixelsPerMeter);

    // Draw player ship (always at center)
    this._drawPlayerShip(ctx, centerX, centerY, playerHeading, playerVel, pixelsPerMeter);

    // Draw compass
    this._drawCompass(ctx, w, h);
  }

  _drawEnvironment(ctx, playerPos, centerX, centerY, pixelsPerMeter) {
    // Environment state comes from the top-level telemetry, not from
    // the ship state.  stateManager._state holds the full snapshot.
    const state = stateManager.getState();
    const env = state?.environment;
    if (!env) return;

    // --- Hazard zones: rendered as translucent circles ---
    // Draw BEHIND asteroids so asteroids are visible inside zones.
    const zones = env.hazard_zones || [];
    for (const zone of zones) {
      const c = zone.center;
      if (!c) continue;
      const sx = centerX + (c.x - playerPos.x) * pixelsPerMeter;
      const sy = centerY - (c.z - playerPos.z) * pixelsPerMeter;
      const sr = zone.radius * pixelsPerMeter;

      // Skip zones too small to see (< 2px) or entirely off-screen
      if (sr < 2) continue;

      ctx.save();
      ctx.beginPath();
      ctx.arc(sx, sy, sr, 0, Math.PI * 2);

      // Color by type: radiation=yellow, debris=orange, nebula=blue
      const t = zone.hazard_type;
      if (t === "radiation") {
        ctx.fillStyle = "rgba(200, 200, 50, 0.10)";
        ctx.strokeStyle = "rgba(200, 200, 50, 0.35)";
      } else if (t === "debris") {
        ctx.fillStyle = "rgba(200, 120, 40, 0.10)";
        ctx.strokeStyle = "rgba(200, 120, 40, 0.35)";
      } else if (t === "nebula") {
        ctx.fillStyle = "rgba(60, 100, 200, 0.12)";
        ctx.strokeStyle = "rgba(60, 100, 200, 0.30)";
      } else {
        ctx.fillStyle = "rgba(150, 150, 150, 0.08)";
        ctx.strokeStyle = "rgba(150, 150, 150, 0.2)";
      }

      ctx.fill();
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);

      // Label at top of zone circle
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = "9px monospace";
      ctx.textAlign = "center";
      ctx.fillText(t.toUpperCase(), sx, sy - sr - 4);

      ctx.restore();
    }

    // --- Asteroid fields: each asteroid rendered as a grey dot ---
    // Only render asteroids that are on-screen to avoid GPU pressure
    // from hundreds of off-screen draw calls.
    const fields = env.asteroid_fields || [];
    const canvasW = ctx.canvas.width;
    const canvasH = ctx.canvas.height;

    ctx.fillStyle = "rgba(120, 120, 130, 0.6)";
    for (const field of fields) {
      const asteroids = field.asteroids || [];
      for (const ast of asteroids) {
        const ax = centerX + (ast.position.x - playerPos.x) * pixelsPerMeter;
        const ay = centerY - (ast.position.z - playerPos.z) * pixelsPerMeter;

        // Cull off-screen asteroids (with generous margin)
        if (ax < -20 || ax > canvasW + 20 || ay < -20 || ay > canvasH + 20) continue;

        // Size: physical radius scaled to screen, clamped 1-6 px
        const ar = Math.max(1, Math.min(6, ast.radius * pixelsPerMeter));

        ctx.beginPath();
        ctx.arc(ax, ay, ar, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  _drawGrid(ctx, w, h, centerX, centerY, scale, pixelsPerMeter) {
    ctx.strokeStyle = "rgba(30, 30, 50, 0.4)";
    ctx.lineWidth = 1;

    // Calculate grid spacing based on scale
    let gridSpacing = scale / 4;
    const gridPixels = gridSpacing * pixelsPerMeter;

    // Draw vertical lines
    for (let x = centerX % gridPixels; x < w; x += gridPixels) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }

    // Draw horizontal lines
    for (let y = centerY % gridPixels; y < h; y += gridPixels) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
  }

  _drawRangeRings(ctx, centerX, centerY, scale, pixelsPerMeter) {
    ctx.strokeStyle = "rgba(0, 170, 255, 0.2)";
    ctx.lineWidth = 1;

    // Draw range rings at 25%, 50%, 75%, 100% of scale
    [0.25, 0.5, 0.75, 1.0].forEach(fraction => {
      const radius = scale * fraction * pixelsPerMeter;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();

      // Label
      if (fraction === 0.5 || fraction === 1.0) {
        const dist = scale * fraction;
        let label;
        if (dist >= 1000) {
          label = `${(dist / 1000).toFixed(1)} km`;
        } else {
          label = `${dist.toFixed(0)} m`;
        }
        ctx.fillStyle = "rgba(0, 170, 255, 0.4)";
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillText(label, centerX + radius + 4, centerY - 4);
      }
    });
  }

  _drawWeaponArcs(ctx, centerX, centerY, scale, pixelsPerMeter) {
    const pdcRadiusPx = WEAPON_RANGES.PDC * pixelsPerMeter;
    const railgunRadiusPx = WEAPON_RANGES.RAILGUN * pixelsPerMeter;

    // Only draw if the ring would be at least a few pixels (visible on screen)
    const MIN_VISIBLE_RADIUS = 4;

    // PDC engagement zone — semi-transparent red filled circle
    if (pdcRadiusPx >= MIN_VISIBLE_RADIUS && WEAPON_RANGES.PDC <= scale * 2) {
      ctx.fillStyle = "rgba(255, 68, 68, 0.05)";
      ctx.beginPath();
      ctx.arc(centerX, centerY, pdcRadiusPx, 0, Math.PI * 2);
      ctx.fill();

      // PDC range ring
      ctx.strokeStyle = "rgba(255, 68, 68, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.arc(centerX, centerY, pdcRadiusPx, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = "rgba(255, 68, 68, 0.6)";
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillText("PDC 5km", centerX + pdcRadiusPx + 4, centerY - 4);
    }

    // Railgun engagement zone — amber ring outline only (no fill, too large)
    if (railgunRadiusPx >= MIN_VISIBLE_RADIUS && WEAPON_RANGES.RAILGUN <= scale * 2) {
      ctx.strokeStyle = "rgba(255, 170, 0, 0.35)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([8, 6]);
      ctx.beginPath();
      ctx.arc(centerX, centerY, railgunRadiusPx, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = "rgba(255, 170, 0, 0.6)";
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillText("RAILGUN 500km", centerX + railgunRadiusPx + 4, centerY - 4);
    }
  }

  /**
   * Draw own ship trajectory projection — dotted line showing future position
   * based on current velocity, projected forward in time.
   */
  _drawTrajectoryProjection(ctx, centerX, centerY, velocity, pixelsPerMeter, scale) {
    const velMag = Math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2);
    if (velMag < 0.1) return;

    ctx.save();
    ctx.strokeStyle = "rgba(0, 170, 255, 0.3)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();

    let prevX = centerX;
    let prevY = centerY;
    let drawn = false;

    for (let i = 1; i <= TRAJECTORY_STEPS; i++) {
      const t = (TRAJECTORY_SECONDS / TRAJECTORY_STEPS) * i;
      const futureX = velocity.x * t * pixelsPerMeter;
      const futureZ = velocity.z * t * pixelsPerMeter;

      const sx = centerX + futureX;
      const sy = centerY - futureZ;

      // Skip if projected point is way off screen
      if (Math.abs(sx - centerX) > this._canvasWidth || Math.abs(sy - centerY) > this._canvasHeight) {
        break;
      }

      if (!drawn) {
        ctx.moveTo(prevX, prevY);
        drawn = true;
      }
      ctx.lineTo(sx, sy);
      prevX = sx;
      prevY = sy;
    }

    if (drawn) {
      ctx.stroke();

      // Draw time markers at 15s and 30s and 60s
      ctx.fillStyle = "rgba(0, 170, 255, 0.5)";
      ctx.font = "9px 'JetBrains Mono', monospace";
      for (const t of [15, 30, 60]) {
        if (t > TRAJECTORY_SECONDS) break;
        const mx = centerX + velocity.x * t * pixelsPerMeter;
        const my = centerY - velocity.z * t * pixelsPerMeter;
        if (Math.abs(mx - centerX) < this._canvasWidth && Math.abs(my - centerY) < this._canvasHeight) {
          ctx.beginPath();
          ctx.arc(mx, my, 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillText(`${t}s`, mx + 5, my - 3);
        }
      }
    }

    ctx.setLineDash([]);
    ctx.restore();
  }

  /**
   * Draw firing solution confidence cones from player to locked target.
   * The cone width reflects the hit probability — narrow = high confidence.
   */
  _drawFiringSolutions(ctx, centerX, centerY, playerPos, contacts, pixelsPerMeter, scale) {
    const targeting = stateManager.getTargeting();
    if (!targeting || !targeting.solutions) return;
    if (targeting.lock_state !== "locked" && targeting.lock_state !== "acquiring") return;

    const targetId = targeting.locked_target;
    if (!targetId) return;

    // Find the target contact
    const targetContact = contacts.find(c => c.id === targetId);
    if (!targetContact) return;

    const targetPos = this._resolveContactPosition(targetContact, playerPos);
    const dx = targetPos.x - playerPos.x;
    const dz = targetPos.z - playerPos.z;
    const dist = Math.sqrt(dx * dx + dz * dz);
    if (dist < 1) return;

    const angleToTarget = Math.atan2(dx, -dz); // screen-space angle

    for (const [weaponId, solution] of Object.entries(targeting.solutions)) {
      if (!solution) continue;
      const confidence = solution.confidence || solution.hit_probability || 0;
      if (confidence <= 0) continue;

      // Cone half-angle: high confidence = narrow cone, low = wide
      // At 1.0 confidence: ~2 degrees. At 0.1 confidence: ~20 degrees.
      const halfAngle = ((1 - confidence) * 18 + 2) * (Math.PI / 180);

      // Choose color based on weapon type
      let color;
      if (weaponId.includes("pdc")) {
        color = `rgba(255, 68, 68, ${0.08 + confidence * 0.12})`;
      } else {
        color = `rgba(255, 170, 0, ${0.08 + confidence * 0.12})`;
      }

      // Cone length: distance to target in pixels, capped
      const coneLengthPx = Math.min(dist * pixelsPerMeter, Math.min(this._canvasWidth, this._canvasHeight));

      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(angleToTarget);

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(Math.sin(halfAngle) * coneLengthPx, -coneLengthPx);
      ctx.lineTo(-Math.sin(halfAngle) * coneLengthPx, -coneLengthPx);
      ctx.closePath();
      ctx.fill();

      // Draw confidence label near the base of the cone
      const labelDist = Math.min(coneLengthPx * 0.3, 60);
      ctx.rotate(-angleToTarget);
      const lx = Math.sin(angleToTarget) * labelDist;
      const ly = -Math.cos(angleToTarget) * labelDist;
      ctx.fillStyle = weaponId.includes("pdc") ? "rgba(255, 68, 68, 0.7)" : "rgba(255, 170, 0, 0.7)";
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const pct = (confidence * 100).toFixed(0);
      const shortName = weaponId.includes("pdc") ? "PDC" : "RG";
      ctx.fillText(`${shortName} ${pct}%`, lx + 8, ly);
      ctx.textAlign = "start";

      ctx.restore();
    }
  }

  /**
   * Draw active projectiles on the map.
   */
  _drawProjectiles(ctx, playerPos, centerX, centerY, pixelsPerMeter) {
    const projectiles = stateManager.getProjectiles();
    if (!projectiles || projectiles.length === 0) return;

    for (const proj of projectiles) {
      const pos = proj.position;
      if (!pos) continue;

      const relX = (pos.x - playerPos.x) * pixelsPerMeter;
      const relZ = (pos.z - playerPos.z) * pixelsPerMeter;
      const sx = centerX + relX;
      const sy = centerY - relZ;

      // Skip if off-screen
      if (sx < -10 || sx > this._canvasWidth + 10 ||
          sy < -10 || sy > this._canvasHeight + 10) {
        continue;
      }

      // Draw projectile as a small bright dot with trail
      // get_state() returns "weapon" (weapon_name), not "type"
      const projWeapon = (proj.weapon || proj.type || "").toLowerCase();
      let color = "#ffffff";
      if (projWeapon.includes("railgun") || projWeapon.includes("kinetic")) {
        color = "#ffaa00";
      } else if (projWeapon.includes("pdc")) {
        color = "#ff6666";
      } else if (projWeapon.includes("torpedo") || projWeapon.includes("missile")) {
        color = "#ff4444";
      }

      // Velocity trail
      if (proj.velocity) {
        const vel = proj.velocity;
        const velMag = Math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2);
        if (velMag > 1) {
          const velAngle = Math.atan2(vel.x, vel.z);
          const trailLen = Math.min(velMag * pixelsPerMeter * 0.5, 20);
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.4;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(
            sx - Math.sin(velAngle) * trailLen,
            sy + Math.cos(velAngle) * trailLen
          );
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }

      // Projectile dot
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(sx, sy, 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  /**
   * Draw active torpedoes on the map.
   * Torpedoes are rendered larger than projectiles with a diamond shape,
   * color-coded by state: green (boost), blue (midcourse), red (terminal).
   * A dashed line connects each torpedo to its target contact.
   */
  _drawTorpedoes(ctx, playerPos, centerX, centerY, pixelsPerMeter) {
    const torpedoes = stateManager.getTorpedoes();
    if (!torpedoes || torpedoes.length === 0) return;

    const shipId = stateManager.getShipState()?.id || "";

    for (const torp of torpedoes) {
      const pos = torp.position;
      if (!pos) continue;

      const relX = (pos.x - playerPos.x) * pixelsPerMeter;
      const relZ = (pos.z - playerPos.z) * pixelsPerMeter;
      const sx = centerX + relX;
      const sy = centerY - relZ;

      // Skip if off-screen
      if (sx < -20 || sx > this._canvasWidth + 20 ||
          sy < -20 || sy > this._canvasHeight + 20) {
        continue;
      }

      const isMissile = torp.munition_type === "missile";

      // Color by state and munition type:
      // Torpedoes: boost=green, midcourse=blue, terminal=pulsing red
      // Missiles: boost=orange, midcourse=amber, terminal=pulsing red-orange
      const state = (torp.state || "boost").toLowerCase();
      let color;
      if (state === "terminal") {
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 150);
        color = isMissile
          ? `rgba(255, 100, 0, ${0.5 + pulse * 0.5})`
          : `rgba(255, 68, 68, ${0.5 + pulse * 0.5})`;
      } else if (state === "midcourse") {
        color = isMissile ? "#cc8800" : "#00aaff";
      } else {
        color = isMissile ? "#ff8800" : "#00ff88";
      }

      const isIncoming = torp.target === shipId;

      // Velocity trail (longer than projectiles -- ordnance is a bigger threat)
      if (torp.velocity) {
        const vel = torp.velocity;
        const velMag = Math.sqrt(vel.x ** 2 + (vel.y || 0) ** 2 + vel.z ** 2);
        if (velMag > 1) {
          const velAngle = Math.atan2(vel.x, vel.z);
          const trailLen = Math.min(velMag * pixelsPerMeter * 0.8, 30);
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.4;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(
            sx - Math.sin(velAngle) * trailLen,
            sy + Math.cos(velAngle) * trailLen
          );
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }

      const size = isIncoming ? 5 : 4;
      ctx.fillStyle = color;

      if (isMissile) {
        // Draw missile as an arrow/triangle pointing in velocity direction
        ctx.beginPath();
        ctx.moveTo(sx, sy - size * 1.3);     // tip
        ctx.lineTo(sx - size, sy + size);     // bottom-left
        ctx.lineTo(sx + size, sy + size);     // bottom-right
        ctx.closePath();
        ctx.fill();
      } else {
        // Draw torpedo as a diamond (distinct from round projectile dots)
        ctx.beginPath();
        ctx.moveTo(sx, sy - size);
        ctx.lineTo(sx + size, sy);
        ctx.lineTo(sx, sy + size);
        ctx.lineTo(sx - size, sy);
        ctx.closePath();
        ctx.fill();
      }

      // Outline for incoming threats
      if (isIncoming) {
        ctx.strokeStyle = isMissile ? "#ff6600" : "#ff4444";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Label: ordnance ID + state, prefixed with type for missiles
      const typePrefix = isMissile ? "MSL " : "";
      ctx.fillStyle = color;
      ctx.font = "9px monospace";
      ctx.textAlign = "left";
      ctx.fillText(`${typePrefix}${torp.id} [${state.toUpperCase()}]`, sx + size + 3, sy + 3);
    }
  }

  _drawPlayerShip(ctx, centerX, centerY, heading, velocity, pixelsPerMeter) {
    ctx.save();
    ctx.translate(centerX, centerY);

    // Heading indicator
    if (this._showHeading) {
      // Yaw=0 is +X (east) in physics, but rotate(0) draws up (+Z/north on canvas).
      // Subtract 90 degrees to align heading arrow with the physics convention.
      const headingRad = (heading * Math.PI) / 180 - Math.PI / 2;
      ctx.rotate(headingRad);
      ctx.strokeStyle = "#00aaff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -30);
      ctx.stroke();

      // Heading arrow
      ctx.beginPath();
      ctx.moveTo(0, -30);
      ctx.lineTo(-5, -22);
      ctx.lineTo(5, -22);
      ctx.closePath();
      ctx.fillStyle = "#00aaff";
      ctx.fill();
      ctx.rotate(-headingRad);
    }

    // Player ship icon (triangle)
    ctx.fillStyle = "#00aaff";
    ctx.beginPath();
    ctx.moveTo(0, -8);
    ctx.lineTo(-6, 6);
    ctx.lineTo(6, 6);
    ctx.closePath();
    ctx.fill();

    // Center dot
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(0, 0, 2, 0, Math.PI * 2);
    ctx.fill();

    // Velocity vector
    if (this._showVelocityVectors) {
      const velMag = Math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2);
      if (velMag > 0.1) {
        // Use X-Z plane for 2D map (Y is "up" in 3D space)
        const velAngle = Math.atan2(velocity.x, velocity.z);
        const velLength = Math.min(velMag * pixelsPerMeter * 10, 60); // Scale and cap

        ctx.strokeStyle = "#00ff88";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        const vx = Math.sin(velAngle) * velLength;
        const vy = -Math.cos(velAngle) * velLength;
        ctx.lineTo(vx, vy);
        ctx.stroke();

        // Velocity arrow head
        ctx.save();
        ctx.translate(vx, vy);
        ctx.rotate(velAngle);
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(-3, 6);
        ctx.lineTo(3, 6);
        ctx.closePath();
        ctx.fillStyle = "#00ff88";
        ctx.fill();
        ctx.restore();
      }
    }

    ctx.restore();
  }

  _drawContact(ctx, contact, playerPos, centerX, centerY, pixelsPerMeter, playerVel, scale) {
    // Calculate relative position — reconstruct from distance/bearing if position is missing
    const contactPos = this._resolveContactPosition(contact, playerPos);
    const relX = (contactPos.x - playerPos.x) * pixelsPerMeter;
    const relZ = (contactPos.z - playerPos.z) * pixelsPerMeter;

    const screenX = centerX + relX;
    const screenY = centerY - relZ; // Invert Z for screen coords

    // Skip if off-screen
    if (screenX < -20 || screenX > this._canvasWidth + 20 ||
        screenY < -20 || screenY > this._canvasHeight + 20) {
      return;
    }

    // Determine color based on faction/IFF
    const color = this._getContactColor(contact);
    const confidence = contact.confidence ?? 1.0;

    const iffType = this._getContactIFF(contact);

    // Draw error ellipse for uncertain contacts (confidence < 0.8)
    if (confidence < 0.8) {
      this._drawErrorEllipse(ctx, screenX, screenY, contact, pixelsPerMeter, color);
    }

    // Draw contact blip — alpha scaled by confidence
    const baseAlpha = 0.4 + confidence * 0.6;
    ctx.globalAlpha = baseAlpha;
    ctx.fillStyle = color;
    ctx.strokeStyle = color;

    if (iffType === "friendly") {
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(screenX, screenY - 8);
      ctx.lineTo(screenX + 8, screenY);
      ctx.lineTo(screenX, screenY + 8);
      ctx.lineTo(screenX - 8, screenY);
      ctx.closePath();
      ctx.stroke();
      ctx.globalAlpha = baseAlpha * 0.3;
      ctx.fill();
    } else if (iffType === "hostile") {
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      const s = 10;
      ctx.rect(screenX - s, screenY - s, s * 2, s * 2);
      ctx.stroke();
      ctx.globalAlpha = baseAlpha * 0.2;
      ctx.fill();
    } else if (iffType === "unknown") {
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.arc(screenX, screenY, 8, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = "8px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("?", screenX, screenY + 1);
    } else {
      // Neutral / simple fallback
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(screenX, screenY, 6, 0, Math.PI * 2);
      ctx.stroke();
    }
    
    ctx.globalAlpha = 1;

    // Contact velocity vector
    if (this._showVelocityVectors && contact.velocity) {
      const vel = contact.velocity;
      const velMag = Math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2);
      if (velMag > 0.1) {
        const velAngle = Math.atan2(vel.x, vel.z);
        const velLength = Math.min(velMag * pixelsPerMeter * 10, 40);

        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.6;
        ctx.beginPath();
        ctx.moveTo(screenX, screenY);
        ctx.lineTo(
          screenX + Math.sin(velAngle) * velLength,
          screenY - Math.cos(velAngle) * velLength
        );
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }

    // Classification label: name/id + class + detection method
    this._drawContactLabel(ctx, contact, screenX, screenY, color, confidence);

    // Weapon engagement ring around contacts within range
    if (this._showWeaponArcs) {
      const dx = contactPos.x - playerPos.x;
      const dz = contactPos.z - playerPos.z;
      const distance = Math.sqrt(dx * dx + dz * dz);

      if (distance <= WEAPON_RANGES.PDC) {
        ctx.strokeStyle = "rgba(255, 68, 68, 0.8)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(screenX, screenY, 10, 0, Math.PI * 2);
        ctx.stroke();
      } else if (distance <= WEAPON_RANGES.RAILGUN) {
        ctx.strokeStyle = "rgba(255, 170, 0, 0.8)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(screenX, screenY, 10, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // Highlight locked target
    const targeting = stateManager.getTargeting();
    if (targeting?.locked_target === contact.id &&
        (targeting.lock_state === "locked" || targeting.lock_state === "acquiring")) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      // Draw targeting brackets
      const bs = 12;
      // Top-left
      ctx.moveTo(screenX - bs, screenY - bs + 4);
      ctx.lineTo(screenX - bs, screenY - bs);
      ctx.lineTo(screenX - bs + 4, screenY - bs);
      // Top-right
      ctx.moveTo(screenX + bs - 4, screenY - bs);
      ctx.lineTo(screenX + bs, screenY - bs);
      ctx.lineTo(screenX + bs, screenY - bs + 4);
      // Bottom-right
      ctx.moveTo(screenX + bs, screenY + bs - 4);
      ctx.lineTo(screenX + bs, screenY + bs);
      ctx.lineTo(screenX + bs - 4, screenY + bs);
      // Bottom-left
      ctx.moveTo(screenX - bs + 4, screenY + bs);
      ctx.lineTo(screenX - bs, screenY + bs);
      ctx.lineTo(screenX - bs, screenY + bs - 4);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Store screen position for click detection (in separate map, not on frozen contact)
    this._contactScreenPositions.set(contact.id, { x: screenX, y: screenY });
  }

  /**
   * Get contact IFF classification.
   */
  _getContactIFF(contact) {
    const faction = contact.faction?.toLowerCase() || contact.iff?.toLowerCase() || "";
    if (faction === "player") return "player";
    if (faction.includes("friend") || faction.includes("ally")) return "friendly";
    if (faction.includes("host") || faction.includes("enemy")) return "hostile";
    if (faction.includes("unknown")) return "unknown";
    return "neutral";
  }

  /**
   * Get contact color based on faction/IFF.
   */
  _getContactColor(contact) {
    const iff = this._getContactIFF(contact);
    if (iff === "friendly" || iff === "player") return "#00ff88";
    if (iff === "hostile") return "#ff4444";
    if (iff === "unknown") return "#ffaa00";
    return "#888899";
  }

  /**
   * Draw error ellipse around an uncertain contact.
   * Size scales inversely with confidence and proportionally with distance.
   */
  _drawErrorEllipse(ctx, screenX, screenY, contact, pixelsPerMeter, color) {
    const confidence = contact.confidence ?? 1.0;
    // Error radius: lower confidence = bigger uncertainty zone
    // Base error is proportional to distance and inversely to confidence
    const distance = contact.distance || 1000;
    // Uncertainty in meters: at 0 confidence, ~20% of distance; at 0.8, ~2%
    const uncertaintyMeters = distance * (1 - confidence) * 0.2;
    const radiusPx = Math.max(8, Math.min(uncertaintyMeters * pixelsPerMeter, 60));

    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.25;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    // Slight ellipse (wider along bearing axis to reflect range uncertainty)
    ctx.ellipse(screenX, screenY, radiusPx, radiusPx * 0.7, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Filled translucent interior
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.05;
    ctx.fill();

    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /**
   * Draw classification label for a contact.
   * Shows: name/ID, classification, and detection method indicator.
   */
  _drawContactLabel(ctx, contact, screenX, screenY, color, confidence) {
    const name = contact.name || contact.id || "Unknown";
    const classification = contact.classification || contact.class || contact.type || "";
    const method = contact.detection_method || "";

    // Method indicator prefix
    let methodPrefix = "";
    if (method === "passive" || method === "ir") {
      methodPrefix = "[P] ";
    } else if (method === "active" || method === "radar") {
      methodPrefix = "[A] ";
    } else if (method === "visual") {
      methodPrefix = "[V] ";
    }

    // Build label text
    let label = methodPrefix + name;
    if (classification && classification !== name) {
      label += ` (${classification})`;
    }

    // Determine Bearing if available
    let bearingText = "";
    if (contact.bearing != null) {
      const yawDeg = typeof contact.bearing === "object" ? (contact.bearing.yaw || 0) : contact.bearing;
      const bstr = ((yawDeg % 360) + 360) % 360;
      bearingText = `BRG ${bstr.toFixed(0).padStart(3, "0")}°`;
    }

    // Labels next to contact
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    
    // Primary Name / Method Label
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.5 + confidence * 0.5;
    ctx.fillText(label, screenX + 12, screenY - 6);
    
    // Bearing Label directly below
    if (bearingText) {
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.globalAlpha = 0.5;
      ctx.fillText(bearingText, screenX + 12, screenY + 6);
    }

    if (confidence < 0.95) {
      // Tiny confidence indicator
      const confText = `${(confidence * 100).toFixed(0)}%`;
      ctx.fillStyle = confidence > 0.5 ? "rgba(0, 170, 255, 0.6)" : "rgba(255, 170, 0, 0.6)";
      ctx.font = "8px 'JetBrains Mono', monospace";
      ctx.fillText(confText, screenX + 8, screenY + 8);
    }

    ctx.globalAlpha = 1;
  }

  _drawCompass(ctx, w, h) {
    const compassSize = 30;
    const margin = 10;
    const cx = w - compassSize - margin;
    const cy = compassSize + margin;

    // Background
    ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
    ctx.beginPath();
    ctx.arc(cx, cy, compassSize, 0, Math.PI * 2);
    ctx.fill();

    // Border
    ctx.strokeStyle = "rgba(0, 170, 255, 0.3)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Cardinal directions
    ctx.fillStyle = "#888899";
    ctx.font = "bold 10px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("N", cx, cy - compassSize + 10);
    ctx.fillText("S", cx, cy + compassSize - 10);
    ctx.fillStyle = "#555566";
    ctx.fillText("E", cx + compassSize - 10, cy);
    ctx.fillText("W", cx - compassSize + 10, cy);
  }

  /**
   * Draw kill confirmation explosion effects.
   * Each explosion is an expanding ring with a fading flash at the contact's
   * last known world position. Expired explosions are pruned.
   */
  _drawExplosions(ctx, playerPos, centerX, centerY, pixelsPerMeter) {
    const now = performance.now();
    // Prune expired explosions
    this._explosions = this._explosions.filter(e => (now - e.startTime) < e.duration);

    for (const explosion of this._explosions) {
      const elapsed = now - explosion.startTime;
      const progress = elapsed / explosion.duration; // 0..1

      // World-to-screen transform
      const relX = (explosion.position.x - playerPos.x) * pixelsPerMeter;
      const relZ = (explosion.position.z - playerPos.z) * pixelsPerMeter;
      const sx = centerX + relX;
      const sy = centerY - relZ;

      // Skip if off-screen
      if (sx < -100 || sx > this._canvasWidth + 100 ||
          sy < -100 || sy > this._canvasHeight + 100) {
        continue;
      }

      ctx.save();

      // Phase 1 (0-0.15): bright flash — white/yellow radial burst
      if (progress < 0.15) {
        const flashProgress = progress / 0.15;
        const flashRadius = 5 + flashProgress * 25;
        const flashAlpha = 1.0 - flashProgress * 0.3;
        const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, flashRadius);
        grad.addColorStop(0, `rgba(255, 255, 200, ${flashAlpha})`);
        grad.addColorStop(0.4, `rgba(255, 160, 40, ${flashAlpha * 0.7})`);
        grad.addColorStop(1, `rgba(255, 68, 0, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(sx, sy, flashRadius, 0, Math.PI * 2);
        ctx.fill();
      }

      // Phase 2 (0-1.0): expanding ring
      const ringRadius = 8 + progress * 50;
      const ringAlpha = Math.max(0, 0.8 * (1 - progress));
      ctx.strokeStyle = `rgba(255, 100, 30, ${ringAlpha})`;
      ctx.lineWidth = Math.max(0.5, 3 * (1 - progress));
      ctx.beginPath();
      ctx.arc(sx, sy, ringRadius, 0, Math.PI * 2);
      ctx.stroke();

      // Secondary inner ring (slightly delayed)
      if (progress > 0.1) {
        const innerProgress = (progress - 0.1) / 0.9;
        const innerRadius = 4 + innerProgress * 35;
        const innerAlpha = Math.max(0, 0.5 * (1 - innerProgress));
        ctx.strokeStyle = `rgba(255, 200, 60, ${innerAlpha})`;
        ctx.lineWidth = Math.max(0.5, 2 * (1 - innerProgress));
        ctx.beginPath();
        ctx.arc(sx, sy, innerRadius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Fading debris dots (8 particles expanding outward)
      if (progress < 0.8) {
        const particleAlpha = Math.max(0, 0.7 * (1 - progress / 0.8));
        ctx.fillStyle = `rgba(255, 120, 40, ${particleAlpha})`;
        const numParticles = 8;
        for (let i = 0; i < numParticles; i++) {
          const angle = (i / numParticles) * Math.PI * 2 + 0.3; // slight offset so it doesn't look too regular
          const dist = 6 + progress * 45 * (0.7 + 0.3 * Math.sin(i * 1.7));
          const px = sx + Math.cos(angle) * dist;
          const py = sy + Math.sin(angle) * dist;
          const dotSize = Math.max(0.5, 2 * (1 - progress));
          ctx.beginPath();
          ctx.arc(px, py, dotSize, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // "KILL" label that fades in then out
      if (progress > 0.1 && progress < 0.7) {
        const labelProgress = (progress - 0.1) / 0.6;
        const labelAlpha = labelProgress < 0.3
          ? labelProgress / 0.3  // fade in
          : 1.0 - (labelProgress - 0.3) / 0.7; // fade out
        ctx.fillStyle = `rgba(255, 68, 68, ${Math.max(0, labelAlpha * 0.8)})`;
        ctx.font = "bold 11px 'JetBrains Mono', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText("KILL", sx, sy - ringRadius - 4);
      }

      ctx.restore();
    }

    // Request another frame if explosions are still active (keeps animation smooth
    // even when no state updates are arriving from the server)
    if (this._explosions.length > 0) {
      requestAnimationFrame(() => this._draw());
    }
  }

  _handleCanvasClick(e) {
    const rect = this._canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const contacts = stateManager.getContacts() || [];
    let clickedContact = null;

    // Check if click is near any contact using stored screen positions
    for (const contact of contacts) {
      const pos = this._contactScreenPositions.get(contact.id);
      if (pos) {
        const dx = x - pos.x;
        const dy = y - pos.y;
        if (Math.sqrt(dx * dx + dy * dy) < 15) {
          clickedContact = contact;
          break;
        }
      }
    }

    this._selectedContact = clickedContact;
    this._updateContactInfo(clickedContact);

    // Dispatch contact-selected event for other components (targeting display etc.)
    if (clickedContact) {
      document.dispatchEvent(new CustomEvent("contact-selected", {
        detail: { contactId: clickedContact.id }
      }));
    }
  }

  _updateContactInfo(contact) {
    const infoPanel = this.shadowRoot.getElementById("contact-info");

    if (!contact) {
      infoPanel.classList.remove("visible");
      return;
    }

    infoPanel.classList.add("visible");

    // Calculate distance and bearing from player
    const ship = stateManager.getShipState();
    const playerPos = ship?.position || { x: 0, y: 0, z: 0 };
    const contactPos = this._resolveContactPosition(contact, playerPos);

    const dx = contactPos.x - playerPos.x;
    const dz = contactPos.z - playerPos.z;
    const distance = Math.sqrt(dx * dx + dz * dz);
    const bearing = ((Math.atan2(dx, dz) * 180 / Math.PI) + 360) % 360;

    const contactVel = contact.velocity || { x: 0, y: 0, z: 0 };
    const speed = Math.sqrt(contactVel.x ** 2 + contactVel.y ** 2 + contactVel.z ** 2);

    // Update info panel
    this.shadowRoot.getElementById("contact-name").textContent = contact.name || contact.id || "Unknown";
    this.shadowRoot.getElementById("contact-type").textContent = contact.classification || contact.class || contact.type || "---";
    this.shadowRoot.getElementById("contact-distance").textContent = this._formatDistance(distance);
    this.shadowRoot.getElementById("contact-bearing").textContent = `${bearing.toFixed(1)}°`;
    this.shadowRoot.getElementById("contact-velocity").textContent = `${speed.toFixed(1)} m/s`;
    this.shadowRoot.getElementById("contact-confidence").textContent =
      contact.confidence != null ? `${(contact.confidence * 100).toFixed(0)}%` : "---";
    this.shadowRoot.getElementById("contact-method").textContent =
      contact.detection_method || "---";
  }

  _formatDistance(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(2)} km`;
    }
    return `${meters.toFixed(0)} m`;
  }
}

customElements.define("tactical-map", TacticalMap);
export { TacticalMap };
