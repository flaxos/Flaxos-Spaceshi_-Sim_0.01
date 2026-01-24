/**
 * Tactical Map Component
 * 2D overhead mini-map showing ship position and contacts
 */

import { stateManager } from "../js/state-manager.js";

const MAP_SCALE_OPTIONS = [1000, 5000, 10000, 50000, 100000]; // meters per screen radius

class TacticalMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._scaleIndex = 2; // Default 10km
    this._showVelocityVectors = true;
    this._showHeading = true;
    this._showGrid = true;
    this._selectedContact = null;
    this._canvas = null;
    this._ctx = null;
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
        </div>
        <div class="control-group">
          <button class="control-btn" id="toggle-vectors" title="Velocity Vectors">V</button>
          <button class="control-btn" id="toggle-heading" title="Heading Indicator">H</button>
          <button class="control-btn" id="toggle-grid" title="Grid">G</button>
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
    // Zoom controls
    this.shadowRoot.getElementById("zoom-in").addEventListener("click", () => {
      if (this._scaleIndex > 0) {
        this._scaleIndex--;
        this._updateScaleDisplay();
        this._draw();
      }
    });

    this.shadowRoot.getElementById("zoom-out").addEventListener("click", () => {
      if (this._scaleIndex < MAP_SCALE_OPTIONS.length - 1) {
        this._scaleIndex++;
        this._updateScaleDisplay();
        this._draw();
      }
    });

    // Toggle buttons
    const vectorsBtn = this.shadowRoot.getElementById("toggle-vectors");
    const headingBtn = this.shadowRoot.getElementById("toggle-heading");
    const gridBtn = this.shadowRoot.getElementById("toggle-grid");

    vectorsBtn.classList.add("active");
    headingBtn.classList.add("active");
    gridBtn.classList.add("active");

    vectorsBtn.addEventListener("click", () => {
      this._showVelocityVectors = !this._showVelocityVectors;
      vectorsBtn.classList.toggle("active", this._showVelocityVectors);
      this._draw();
    });

    headingBtn.addEventListener("click", () => {
      this._showHeading = !this._showHeading;
      headingBtn.classList.toggle("active", this._showHeading);
      this._draw();
    });

    gridBtn.addEventListener("click", () => {
      this._showGrid = !this._showGrid;
      gridBtn.classList.toggle("active", this._showGrid);
      this._draw();
    });

    // Canvas click for contact selection
    this._canvas.addEventListener("click", (e) => {
      this._handleCanvasClick(e);
    });

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
    ctx.fillStyle = "#0d0d12";
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

    // Draw contacts
    const contacts = stateManager.getContacts() || [];
    contacts.forEach(contact => {
      this._drawContact(ctx, contact, playerPos, centerX, centerY, pixelsPerMeter, playerVel);
    });

    // Draw player ship (always at center)
    this._drawPlayerShip(ctx, centerX, centerY, playerHeading, playerVel, pixelsPerMeter);

    // Draw compass
    this._drawCompass(ctx, w, h);
  }

  _drawGrid(ctx, w, h, centerX, centerY, scale, pixelsPerMeter) {
    ctx.strokeStyle = "rgba(40, 40, 60, 0.5)";
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

  _drawPlayerShip(ctx, centerX, centerY, heading, velocity, pixelsPerMeter) {
    ctx.save();
    ctx.translate(centerX, centerY);

    // Heading indicator
    if (this._showHeading) {
      ctx.rotate((heading * Math.PI) / 180);
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
      ctx.rotate(-(heading * Math.PI) / 180);
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

  _drawContact(ctx, contact, playerPos, centerX, centerY, pixelsPerMeter, playerVel) {
    // Calculate relative position
    const contactPos = contact.position || { x: 0, y: 0, z: 0 };
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
    let color = "#888899"; // neutral
    const faction = contact.faction?.toLowerCase() || contact.iff?.toLowerCase() || "";
    if (faction.includes("friend") || faction.includes("ally") || faction === "player") {
      color = "#00ff88";
    } else if (faction.includes("host") || faction.includes("enemy")) {
      color = "#ff4444";
    } else if (faction.includes("unknown")) {
      color = "#ffaa00";
    }

    // Draw contact blip
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(screenX, screenY, 5, 0, Math.PI * 2);
    ctx.fill();

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

    // Label
    const label = contact.name || contact.id || "Unknown";
    ctx.fillStyle = color;
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillText(label, screenX + 8, screenY + 4);

    // Store screen position for click detection
    contact._screenX = screenX;
    contact._screenY = screenY;
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

  _handleCanvasClick(e) {
    const rect = this._canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const contacts = stateManager.getContacts() || [];
    let clickedContact = null;

    // Check if click is near any contact
    for (const contact of contacts) {
      if (contact._screenX !== undefined) {
        const dx = x - contact._screenX;
        const dy = y - contact._screenY;
        if (Math.sqrt(dx * dx + dy * dy) < 15) {
          clickedContact = contact;
          break;
        }
      }
    }

    this._selectedContact = clickedContact;
    this._updateContactInfo(clickedContact);
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
    const contactPos = contact.position || { x: 0, y: 0, z: 0 };

    const dx = contactPos.x - playerPos.x;
    const dz = contactPos.z - playerPos.z;
    const distance = Math.sqrt(dx * dx + dz * dz);
    const bearing = ((Math.atan2(dx, dz) * 180 / Math.PI) + 360) % 360;

    const contactVel = contact.velocity || { x: 0, y: 0, z: 0 };
    const speed = Math.sqrt(contactVel.x ** 2 + contactVel.y ** 2 + contactVel.z ** 2);

    // Update info panel
    this.shadowRoot.getElementById("contact-name").textContent = contact.name || contact.id || "Unknown";
    this.shadowRoot.getElementById("contact-type").textContent = contact.class || contact.type || "---";
    this.shadowRoot.getElementById("contact-distance").textContent = this._formatDistance(distance);
    this.shadowRoot.getElementById("contact-bearing").textContent = `${bearing.toFixed(1)}°`;
    this.shadowRoot.getElementById("contact-velocity").textContent = `${speed.toFixed(1)} m/s`;
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
