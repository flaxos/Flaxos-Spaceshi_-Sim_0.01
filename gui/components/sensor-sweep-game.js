/**
 * Sensor Sweep Game (ARCADE tier)
 *
 * A radar-sweep mini-game that maps to the passive sensor model.
 * The player rotates a detection cone around a circular display.
 * Contacts appear as sonar-style pings that fade over time. Sectors
 * not swept recently show stale contacts with degraded indicators.
 *
 * Clicking a sector triggers a "focus scan" that pauses the sweep
 * and sends a ping_sensors command. The game is purely visual feedback;
 * actual detection is server-authoritative.
 *
 * State reads:
 *   ship.sensor_contacts — array of {id, bearing, range, name, classification, confidence}
 *
 * Visible only in ARCADE tier (TACTICAL view, DETECT group).
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

// Timing constants
const PING_FADE_MS = 8000;         // How long a contact ping stays bright (ms)
const STALE_THRESHOLD_MS = 12000;  // Contact marked stale after this long without sweep
const FOCUS_DURATION_MS = 2000;    // How long a focus scan lasts
const SECTOR_COUNT = 8;            // 45-degree sectors
const SWEEP_SPEED_DEFAULT = 0.8;   // radians per second

// Visual constants
const BG_COLOR = "#0a0a14";
const RING_COLOR = "rgba(0, 255, 136, 0.08)";
const RING_LABEL_COLOR = "rgba(0, 255, 136, 0.25)";
const SWEEP_COLOR = "#00ff88";
const CONTACT_COLOR_FRESH = "#00ff88";
const CONTACT_COLOR_STALE = "#334455";
const SECTOR_HIGHLIGHT = "rgba(0, 255, 136, 0.06)";
const CENTER_DOT_COLOR = "#00ff88";

class SensorSweepGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._canvas = null;
    this._ctx = null;
    this._animFrame = null;
    this._lastFrameTime = 0;

    // Sweep state
    this._sweepAngle = 0;        // radians, current sweep position (0 = up/north)
    this._sweepSpeed = SWEEP_SPEED_DEFAULT;
    this._sweepDirection = 1;    // 1 = clockwise, -1 = counter-clockwise

    // Contact state: contactId -> {bearing, range, lastPingTime, peakBrightness, name, classification}
    this._contactPings = new Map();

    // Focus scan: clicking a sector
    this._focusSector = null;    // {index, startAngle, endAngle, startTime}

    // Server contacts (updated from stateManager)
    this._serverContacts = [];

    // Subscriptions
    this._unsub = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Interaction state
    this._boundClick = null;
    this._boundTouch = null;
  }

  connectedCallback() {
    this._render();
    this._setupCanvas();
    this._subscribe();
    this._setupInteraction();
    this._startLoop();

    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);
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
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readState();
    });
  }

  /** Read sensor contacts from server telemetry */
  _readState() {
    const ship = stateManager.getShipState();
    if (!ship) return;
    this._serverContacts = ship?.sensor_contacts || [];

    // Update contact counter in DOM
    const counter = this.shadowRoot.querySelector(".contact-count-value");
    if (counter) {
      counter.textContent = this._serverContacts.length;
    }
  }

  _setupCanvas() {
    this._canvas = this.shadowRoot.querySelector("canvas");
    if (!this._canvas) return;

    // Size canvas for crisp rendering on high-DPI displays
    const size = 200;
    const dpr = window.devicePixelRatio || 1;
    this._canvas.width = size * dpr;
    this._canvas.height = size * dpr;
    this._canvas.style.width = `${size}px`;
    this._canvas.style.height = `${size}px`;
    this._ctx = this._canvas.getContext("2d");
    this._ctx.scale(dpr, dpr);
    this._displaySize = size;
  }

  /** Convert a click position on the canvas to a sector index (0-7) */
  _clickToSector(clientX, clientY) {
    const rect = this._canvas.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const dx = (clientX - rect.left) - cx;
    const dy = (clientY - rect.top) - cy;

    // Angle from center, 0 = north (up), clockwise
    let angle = Math.atan2(dx, -dy); // atan2(x, -y) gives 0=north, CW positive
    if (angle < 0) angle += Math.PI * 2;

    const sectorSize = (Math.PI * 2) / SECTOR_COUNT;
    return Math.floor(angle / sectorSize);
  }

  _setupInteraction() {
    if (!this._canvas) return;

    this._boundClick = (e) => {
      const sectorIndex = this._clickToSector(e.clientX, e.clientY);
      this._triggerFocusScan(sectorIndex);
    };
    this._canvas.addEventListener("click", this._boundClick);

    this._boundTouch = (e) => {
      e.preventDefault();
      const touch = e.touches[0];
      if (touch) {
        const sectorIndex = this._clickToSector(touch.clientX, touch.clientY);
        this._triggerFocusScan(sectorIndex);
      }
    };
    this._canvas.addEventListener("touchstart", this._boundTouch, { passive: false });
  }

  /** Focus scan on a sector: pause sweep, highlight sector, send command */
  _triggerFocusScan(sectorIndex) {
    const sectorSize = (Math.PI * 2) / SECTOR_COUNT;
    this._focusSector = {
      index: sectorIndex,
      startAngle: sectorIndex * sectorSize,
      endAngle: (sectorIndex + 1) * sectorSize,
      startTime: performance.now(),
    };

    // Send ping_sensors command (server-authoritative, this is just player intent)
    wsClient.sendShipCommand("ping_sensors", {});

    // Boost any contacts in this sector
    const now = performance.now();
    for (const [id, ping] of this._contactPings) {
      const contactAngle = this._bearingToAngle(ping.bearing);
      if (this._angleInSector(contactAngle, this._focusSector.startAngle, this._focusSector.endAngle)) {
        ping.lastPingTime = now;
        ping.peakBrightness = 1.0;
      }
    }

    // Update sweep rate indicator
    const rateEl = this.shadowRoot.querySelector(".sweep-rate-value");
    if (rateEl) {
      rateEl.textContent = "FOCUSED";
      rateEl.classList.add("focused");
      setTimeout(() => {
        rateEl.textContent = `${this._sweepSpeed.toFixed(1)} rad/s`;
        rateEl.classList.remove("focused");
      }, FOCUS_DURATION_MS);
    }
  }

  /** Convert bearing in degrees (0=north, CW) to radians (0=north, CW) */
  _bearingToAngle(bearingDeg) {
    return ((bearingDeg % 360) * Math.PI) / 180;
  }

  /** Check if an angle falls within a sector arc */
  _angleInSector(angle, startAngle, endAngle) {
    // Normalize to 0-2PI
    const a = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
    const s = ((startAngle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
    const e = ((endAngle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);

    if (s < e) {
      return a >= s && a < e;
    } else {
      // Wraps around 0
      return a >= s || a < e;
    }
  }

  /** Main animation loop */
  _startLoop() {
    const loop = (timestamp) => {
      this._animFrame = requestAnimationFrame(loop);

      if (!this._lastFrameTime) {
        this._lastFrameTime = timestamp;
        return;
      }

      const dt = (timestamp - this._lastFrameTime) / 1000; // seconds
      this._lastFrameTime = timestamp;

      // Update sweep angle (pause during focus scan)
      const now = performance.now();
      const focusing = this._focusSector && (now - this._focusSector.startTime) < FOCUS_DURATION_MS;

      if (!focusing) {
        this._sweepAngle += this._sweepSpeed * this._sweepDirection * dt;
        this._sweepAngle = this._sweepAngle % (Math.PI * 2);
        if (this._sweepAngle < 0) this._sweepAngle += Math.PI * 2;

        // Clear focus sector once expired
        if (this._focusSector && (now - this._focusSector.startTime) >= FOCUS_DURATION_MS) {
          this._focusSector = null;
        }
      }

      // Check if sweep line passes over any contacts
      this._checkSweepHits(now);

      // Draw everything
      this._draw(now);
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  /** Check if the sweep line just passed over any contact bearings */
  _checkSweepHits(now) {
    const sweepWidth = 0.15; // radians — how wide the "hit zone" is per frame

    for (const contact of this._serverContacts) {
      if (contact.bearing == null || contact.range == null) continue;

      const contactAngle = this._bearingToAngle(contact.bearing);
      const diff = Math.abs(this._angleDiff(this._sweepAngle, contactAngle));

      if (diff < sweepWidth) {
        const id = contact.id || contact.contact_id || `${contact.bearing}-${contact.range}`;
        const existing = this._contactPings.get(id);
        const brightness = existing?.peakBrightness || 0;

        this._contactPings.set(id, {
          bearing: contact.bearing,
          range: contact.range,
          name: contact.name || contact.classification || "UNKNOWN",
          classification: contact.classification || "unknown",
          confidence: contact.confidence || 0,
          lastPingTime: now,
          peakBrightness: Math.max(0.8, brightness),
        });
      }
    }

    // Prune contacts that no longer exist on server
    for (const [id] of this._contactPings) {
      const stillExists = this._serverContacts.some(
        (c) => (c.id || c.contact_id || `${c.bearing}-${c.range}`) === id
      );
      if (!stillExists) {
        this._contactPings.delete(id);
      }
    }
  }

  /** Shortest signed angle difference */
  _angleDiff(a, b) {
    let d = b - a;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    return d;
  }

  /** Draw the full radar display */
  _draw(now) {
    const ctx = this._ctx;
    const size = this._displaySize;
    if (!ctx || !size) return;

    const cx = size / 2;
    const cy = size / 2;
    const radius = (size / 2) - 12; // Leave margin for labels

    // Clear
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, size, size);

    // Outer circle
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0, 255, 136, 0.15)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Range rings at 25%, 50%, 75%
    for (const frac of [0.25, 0.5, 0.75]) {
      ctx.beginPath();
      ctx.arc(cx, cy, radius * frac, 0, Math.PI * 2);
      ctx.strokeStyle = RING_COLOR;
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Cardinal bearing labels
    ctx.fillStyle = RING_LABEL_COLOR;
    ctx.font = "9px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const labels = [
      { text: "000", x: cx, y: cy - radius - 6 },
      { text: "090", x: cx + radius + 8, y: cy },
      { text: "180", x: cx, y: cy + radius + 7 },
      { text: "270", x: cx - radius - 8, y: cy },
    ];
    for (const label of labels) {
      ctx.fillText(label.text, label.x, label.y);
    }

    // Focus sector highlight
    if (this._focusSector) {
      const elapsed = now - this._focusSector.startTime;
      if (elapsed < FOCUS_DURATION_MS) {
        const alpha = 0.12 * (1 - elapsed / FOCUS_DURATION_MS);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        // Canvas angles: 0 = right, but our 0 = north (up), so rotate -PI/2
        const drawStart = this._focusSector.startAngle - Math.PI / 2;
        const drawEnd = this._focusSector.endAngle - Math.PI / 2;
        ctx.arc(cx, cy, radius, drawStart, drawEnd);
        ctx.closePath();
        ctx.fillStyle = `rgba(0, 255, 136, ${alpha})`;
        ctx.fill();
      }
    }

    // Sweep trail (fading wedge behind the sweep line)
    this._drawSweepTrail(ctx, cx, cy, radius, now);

    // Sweep line
    const sweepEndX = cx + Math.sin(this._sweepAngle) * radius;
    const sweepEndY = cy - Math.cos(this._sweepAngle) * radius;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(sweepEndX, sweepEndY);
    ctx.strokeStyle = SWEEP_COLOR;
    ctx.lineWidth = 1.5;
    ctx.shadowColor = SWEEP_COLOR;
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Contact pings
    this._drawContacts(ctx, cx, cy, radius, now);

    // Center dot (own ship)
    ctx.beginPath();
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = CENTER_DOT_COLOR;
    ctx.shadowColor = CENTER_DOT_COLOR;
    ctx.shadowBlur = 4;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  /** Draw the fading trail behind the sweep line */
  _drawSweepTrail(ctx, cx, cy, radius, now) {
    const trailAngle = 0.5; // radians of trail behind sweep
    const segments = 12;

    for (let i = 0; i < segments; i++) {
      const frac = i / segments;
      const alpha = 0.12 * (1 - frac);
      const angleStart = this._sweepAngle - (trailAngle * frac) - Math.PI / 2;
      const angleEnd = this._sweepAngle - (trailAngle * (frac + 1 / segments)) - Math.PI / 2;

      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, angleEnd, angleStart);
      ctx.closePath();
      ctx.fillStyle = `rgba(0, 255, 136, ${alpha})`;
      ctx.fill();
    }
  }

  /** Draw all tracked contact pings */
  _drawContacts(ctx, cx, cy, radius, now) {
    // Find max range among contacts to scale display
    let maxRange = 1;
    for (const [, ping] of this._contactPings) {
      if (ping.range > maxRange) maxRange = ping.range;
    }
    // Add 20% padding so contacts don't sit on the edge
    maxRange *= 1.2;

    for (const [id, ping] of this._contactPings) {
      const age = now - ping.lastPingTime;
      const fadeFrac = Math.min(1, age / PING_FADE_MS);
      const isStale = age > STALE_THRESHOLD_MS;

      // Position on display
      const angle = this._bearingToAngle(ping.bearing);
      const dist = Math.min(1, ping.range / maxRange) * radius * 0.9;
      const px = cx + Math.sin(angle) * dist;
      const py = cy - Math.cos(angle) * dist;

      // Brightness: starts at peakBrightness, fades to dim
      const brightness = ping.peakBrightness * (1 - fadeFrac * 0.85);
      const dotRadius = isStale ? 2 : 2.5 + (1 - fadeFrac) * 1.5;

      // Color interpolation: fresh green -> stale gray
      if (isStale) {
        ctx.fillStyle = CONTACT_COLOR_STALE;
      } else {
        const g = Math.floor(255 * brightness);
        const r = Math.floor(80 * (1 - brightness));
        ctx.fillStyle = `rgb(${r}, ${g}, ${Math.floor(136 * brightness)})`;
      }

      // Glow on fresh contacts
      if (!isStale && fadeFrac < 0.3) {
        ctx.shadowColor = SWEEP_COLOR;
        ctx.shadowBlur = 6 * (1 - fadeFrac / 0.3);
      }

      ctx.beginPath();
      ctx.arc(px, py, dotRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Stale indicator: "?" next to dot
      if (isStale) {
        ctx.fillStyle = "rgba(255, 200, 60, 0.6)";
        ctx.font = "bold 8px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText("?", px + 5, py);
      }

      // Contact label (only for fresh, confident contacts)
      if (!isStale && fadeFrac < 0.5 && ping.name && ping.name !== "UNKNOWN") {
        ctx.fillStyle = `rgba(0, 255, 136, ${0.6 * (1 - fadeFrac)})`;
        ctx.font = "7px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(ping.name, px + 5, py + 3);
      }
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          padding: 0;
        }

        .sweep-root {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          padding: 10px;
          user-select: none;
        }

        /* Header bar */
        .sweep-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          width: 100%;
          padding: 0 4px;
        }

        .contact-count {
          color: #667;
          font-size: 0.7rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }

        .contact-count-value {
          color: ${SWEEP_COLOR};
          font-weight: 600;
        }

        .sweep-rate {
          color: #445;
          font-size: 0.65rem;
          letter-spacing: 0.1em;
        }

        .sweep-rate-value {
          color: #556;
          transition: color 0.2s;
        }

        .sweep-rate-value.focused {
          color: ${SWEEP_COLOR};
          text-shadow: 0 0 4px rgba(0, 255, 136, 0.4);
        }

        /* Canvas container */
        .radar-container {
          position: relative;
          width: 200px;
          height: 200px;
          border-radius: 50%;
          overflow: hidden;
          cursor: crosshair;
          box-shadow:
            0 0 20px rgba(0, 255, 136, 0.05),
            inset 0 0 30px rgba(0, 0, 0, 0.5);
        }

        canvas {
          display: block;
          border-radius: 50%;
        }

        /* Footer bar */
        .sweep-footer {
          display: flex;
          justify-content: center;
          width: 100%;
          padding: 0 4px;
        }

        .sweep-hint {
          color: #334;
          font-size: 0.6rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        /* Idle state (no contacts) */
        .idle-state {
          display: flex;
          align-items: center;
          justify-content: center;
          flex-direction: column;
          gap: 6px;
          height: 80px;
          color: #334;
          font-size: 0.7rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          border: 1px dashed #1a1a2e;
          border-radius: 3px;
        }
      </style>

      <div class="sweep-root">
        <div class="sweep-header">
          <span class="contact-count">CONTACTS: <span class="contact-count-value">0</span></span>
          <span class="sweep-rate">SWEEP <span class="sweep-rate-value">${this._sweepSpeed.toFixed(1)} rad/s</span></span>
        </div>

        <div class="radar-container">
          <canvas width="200" height="200"></canvas>
        </div>

        <div class="sweep-footer">
          <span class="sweep-hint">click sector to focus scan</span>
        </div>
      </div>
    `;
  }
}

customElements.define("sensor-sweep-game", SensorSweepGame);
