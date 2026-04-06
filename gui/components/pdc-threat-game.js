/**
 * PDC Threat Triage Game (ARCADE tier)
 *
 * Canvas-based radial threat display where incoming torpedoes and missiles
 * appear as colored pips approaching the ship (center). The player clicks
 * threats to assign PDC engagement priority order (1, 2, 3...).
 *
 * State reads:
 *   stateManager.getTorpedoes() — all active munitions
 *   ship.id — own ship ID to filter incoming threats
 *   weapons.pdc_priority_targets — current server priority order
 *
 * On click: sends set_pdc_priority with ordered torpedo_ids array.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

// Visual constants
const SHIP_RADIUS = 8;            // Center ship pip size
const TORPEDO_RADIUS = 7;         // Torpedo pip size
const MISSILE_RADIUS = 5;         // Missile pip size
const MAX_DISPLAY_RANGE = 50000;  // 50km — threats beyond this are at the edge
const RING_COUNT = 3;             // Concentric range rings
const PRIORITY_LABEL_OFFSET = 10; // Offset for priority number labels
const HIT_RADIUS = 18;            // Click detection radius (px)

class PdcThreatGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._animFrame = null;
    this._lastFrameTime = 0;
    this._canvas = null;
    this._ctx = null;
    this._threats = [];         // Processed threat list for rendering
    this._priorityOrder = [];   // Ordered threat IDs (user-set)
    this._serverPriority = [];  // Server-confirmed priority
    this._ourShipId = "";
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";
    this._canvasWidth = 0;
    this._canvasHeight = 0;
    // Pulse animation for selected threats
    this._pulsePhase = 0;
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.getElementById("threat-canvas");
    this._ctx = this._canvas.getContext("2d");
    this._resizeCanvas();

    this._subscribe();
    this._setupInteraction();
    this._startLoop();

    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);

    // Handle resize
    this._resizeObserver = new ResizeObserver(() => this._resizeCanvas());
    this._resizeObserver.observe(this.shadowRoot.querySelector(".game-wrapper"));
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readState();
    });
  }

  _readState() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    this._ourShipId = ship?.id || ship?.ship_id || "";

    // All active munitions from torpedo manager telemetry
    const allMunitions = stateManager.getTorpedoes() || [];

    // Filter to incoming threats targeting our ship
    this._threats = allMunitions
      .filter((m) => m.alive && m.target === this._ourShipId)
      .map((m) => ({
        id: m.id,
        type: m.munition_type || "torpedo",
        distance: m.distance || 0,
        eta: m.eta,
        closingSpeed: m.closing_speed || 0,
        position: m.position || { x: 0, y: 0, z: 0 },
        armed: m.armed,
      }));

    // Read server-confirmed priority
    const weapons = stateManager.getWeapons();
    const combat = stateManager.getCombat();
    this._serverPriority =
      weapons?.pdc_priority_targets || combat?.pdc_priority_targets || [];

    // Sync local priority with server (remove dead threats)
    const aliveIds = new Set(this._threats.map((t) => t.id));
    this._priorityOrder = this._priorityOrder.filter((id) => aliveIds.has(id));
  }

  _resizeCanvas() {
    const wrapper = this.shadowRoot.querySelector(".game-wrapper");
    if (!wrapper || !this._canvas) return;
    const rect = wrapper.getBoundingClientRect();
    // Square canvas fitting the wrapper
    const size = Math.min(rect.width, rect.height) || 240;
    this._canvas.width = size * window.devicePixelRatio;
    this._canvas.height = size * window.devicePixelRatio;
    this._canvas.style.width = `${size}px`;
    this._canvas.style.height = `${size}px`;
    this._canvasWidth = size;
    this._canvasHeight = size;
  }

  _setupInteraction() {
    this._canvas.addEventListener("click", (e) => {
      const rect = this._canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      this._handleClick(x, y);
    });

    // Touch support for mobile
    this._canvas.addEventListener("touchstart", (e) => {
      e.preventDefault();
      const touch = e.touches[0];
      const rect = this._canvas.getBoundingClientRect();
      const x = touch.clientX - rect.left;
      const y = touch.clientY - rect.top;
      this._handleClick(x, y);
    });
  }

  _handleClick(x, y) {
    const cx = this._canvasWidth / 2;
    const cy = this._canvasHeight / 2;
    const maxR = Math.min(cx, cy) - 12;

    // Find closest threat to click point
    let closest = null;
    let closestDist = Infinity;

    for (const threat of this._threats) {
      const normDist = Math.min(threat.distance / MAX_DISPLAY_RANGE, 1.0);
      // Place threats radially based on distance; angle from position
      const angle = this._threatAngle(threat);
      const r = normDist * maxR;
      const tx = cx + r * Math.cos(angle);
      const ty = cy + r * Math.sin(angle);
      const d = Math.hypot(x - tx, y - ty);
      if (d < HIT_RADIUS && d < closestDist) {
        closest = threat;
        closestDist = d;
      }
    }

    if (!closest) return;

    // Toggle in priority queue
    const idx = this._priorityOrder.indexOf(closest.id);
    if (idx !== -1) {
      this._priorityOrder.splice(idx, 1);
    } else {
      this._priorityOrder.push(closest.id);
    }

    this._sendPriority();
  }

  /** Compute a stable angle for a threat based on its position relative to origin. */
  _threatAngle(threat) {
    const pos = threat.position;
    // Use x/z plane angle (top-down) for radial placement
    return Math.atan2(pos.z || 0, pos.x || 0);
  }

  async _sendPriority() {
    try {
      await wsClient.sendShipCommand("set_pdc_priority", {
        torpedo_ids: this._priorityOrder,
      });
    } catch (error) {
      console.error("PDC priority send failed:", error);
    }
  }

  _startLoop() {
    const loop = (now) => {
      this._animFrame = requestAnimationFrame(loop);
      // Delta-time clamping (cap at 100ms to avoid spiral after tab-away)
      const dt = Math.min((now - (this._lastFrameTime || now)) / 1000, 0.1);
      this._lastFrameTime = now;
      this._pulsePhase += dt * 3;
      this._draw();
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  _draw() {
    const ctx = this._ctx;
    const w = this._canvasWidth;
    const h = this._canvasHeight;
    if (!ctx || w === 0) return;

    const dpr = window.devicePixelRatio;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const maxR = Math.min(cx, cy) - 12;

    // Draw range rings
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    for (let i = 1; i <= RING_COUNT; i++) {
      const r = (i / RING_COUNT) * maxR;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Range labels
    ctx.fillStyle = "rgba(255, 255, 255, 0.2)";
    ctx.font = "9px monospace";
    ctx.textAlign = "left";
    for (let i = 1; i <= RING_COUNT; i++) {
      const r = (i / RING_COUNT) * maxR;
      const rangeKm = ((i / RING_COUNT) * MAX_DISPLAY_RANGE / 1000).toFixed(0);
      ctx.fillText(`${rangeKm}km`, cx + 3, cy - r + 10);
    }

    // Draw crosshairs
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.beginPath();
    ctx.moveTo(cx - maxR, cy);
    ctx.lineTo(cx + maxR, cy);
    ctx.moveTo(cx, cy - maxR);
    ctx.lineTo(cx, cy + maxR);
    ctx.stroke();

    // Draw ship at center
    ctx.fillStyle = "#00ff88";
    ctx.beginPath();
    ctx.arc(cx, cy, SHIP_RADIUS, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#000";
    ctx.font = "bold 8px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("S", cx, cy);

    // Draw threats
    const pulse = 0.5 + 0.5 * Math.sin(this._pulsePhase);

    for (const threat of this._threats) {
      const normDist = Math.min(threat.distance / MAX_DISPLAY_RANGE, 1.0);
      const angle = this._threatAngle(threat);
      const r = normDist * maxR;
      const tx = cx + r * Math.cos(angle);
      const ty = cy + r * Math.sin(angle);

      const isTorpedo = threat.type === "torpedo";
      const baseColor = isTorpedo ? "#ff4444" : "#ff8800";
      const radius = isTorpedo ? TORPEDO_RADIUS : MISSILE_RADIUS;
      const priIdx = this._priorityOrder.indexOf(threat.id);
      const isPrioritized = priIdx !== -1;

      // Glow for prioritized threats
      if (isPrioritized) {
        ctx.save();
        ctx.globalAlpha = 0.3 + 0.2 * pulse;
        ctx.fillStyle = baseColor;
        ctx.beginPath();
        ctx.arc(tx, ty, radius + 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      // Threat pip
      ctx.fillStyle = baseColor;
      ctx.globalAlpha = isPrioritized ? 1.0 : 0.7;
      ctx.beginPath();
      ctx.arc(tx, ty, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1.0;

      // Type label inside pip
      ctx.fillStyle = "#000";
      ctx.font = `bold ${isTorpedo ? 7 : 6}px monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(isTorpedo ? "T" : "M", tx, ty);

      // Priority number
      if (isPrioritized) {
        ctx.fillStyle = "#ffaa00";
        ctx.font = "bold 10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(`${priIdx + 1}`, tx, ty - radius - 2);
      }

      // ETA label
      if (threat.eta != null) {
        ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
        ctx.font = "8px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillText(`${threat.eta.toFixed(0)}s`, tx, ty + radius + 2);
      }
    }

    // Status bar at bottom
    const threatCount = this._threats.length;
    const priCount = this._priorityOrder.length;
    ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    if (threatCount === 0) {
      ctx.fillText("NO INCOMING THREATS", cx, h - 4);
    } else {
      ctx.fillText(
        `${threatCount} INCOMING | ${priCount} PRIORITIZED`,
        cx,
        h - 4
      );
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 100%;
        }

        .game-wrapper {
          position: relative;
          width: 100%;
          aspect-ratio: 1;
          min-height: 200px;
          max-height: 320px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0, 0, 0, 0.4);
          border-radius: 8px;
          overflow: hidden;
        }

        canvas {
          cursor: crosshair;
        }

        .legend {
          display: flex;
          gap: 12px;
          justify-content: center;
          padding: 6px 0 2px;
          font-size: 0.6rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-dim, #888);
        }

        .legend-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .legend-pip {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .legend-pip.torpedo { background: #ff4444; }
        .legend-pip.missile { background: #ff8800; }
        .legend-pip.ship { background: #00ff88; }

        .instructions {
          text-align: center;
          font-size: 0.55rem;
          color: var(--text-dim, #666);
          padding: 2px 8px 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }
      </style>

      <div class="game-wrapper">
        <canvas id="threat-canvas"></canvas>
      </div>
      <div class="legend">
        <span class="legend-item"><span class="legend-pip torpedo"></span> TORPEDO</span>
        <span class="legend-item"><span class="legend-pip missile"></span> MISSILE</span>
        <span class="legend-item"><span class="legend-pip ship"></span> SHIP</span>
      </div>
      <div class="instructions">Click threats to set PDC engagement priority</div>
    `;
  }
}

customElements.define("pdc-threat-game", PdcThreatGame);
