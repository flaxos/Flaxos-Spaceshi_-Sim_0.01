/**
 * Weapon Aiming Panel -- MANUAL tier visual reticle display.
 *
 * Renders a real-time aiming reticle that visualizes the firing solution
 * geometry: ship nose bearing, computed lead angle, confidence cone, and
 * target bearing. The player uses this to understand WHERE the weapon is
 * pointed relative to the intercept solution.
 *
 * This is a display-only component -- all state comes from the server via
 * stateManager.getTargeting() and stateManager.getNavigation(). No server
 * commands are sent; the aiming data is the same firing solution the
 * fire_railgun command uses.
 *
 * Visible only in MANUAL tier (hidden in all other tiers via tiers.css).
 */

import { stateManager } from "../js/state-manager.js";

class WeaponAimingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._tier = window.controlTier || "arcade";
    this._animFrame = null;
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._updateReticle());
    this._onTier = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._onTier);
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
    if (this._onTier) {
      document.removeEventListener("tier-change", this._onTier);
      this._onTier = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
        }

        .aim-container {
          position: relative;
          width: 100%;
          aspect-ratio: 1 / 1;
          max-height: 320px;
          margin: 0 auto;
          overflow: hidden;
        }

        .aim-svg {
          width: 100%;
          height: 100%;
        }

        .no-solution {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 200px;
          color: var(--text-dim, #555566);
          font-style: italic;
          font-size: 0.8rem;
          text-align: center;
        }

        /* Readout row under the reticle */
        .readout-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 4px 8px;
          padding: 8px 4px 4px;
          font-size: 0.65rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .readout-item {
          text-align: center;
        }

        .readout-label {
          color: var(--text-dim, #555566);
          font-size: 0.55rem;
        }

        .readout-value {
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
          font-size: 0.75rem;
        }

        .readout-value.high { color: var(--status-nominal, #00ff88); }
        .readout-value.mid  { color: var(--status-warning, #ffaa00); }
        .readout-value.low  { color: var(--status-critical, #ff4444); }

        /* Status pills */
        .status-row {
          display: flex;
          gap: 6px;
          justify-content: center;
          padding: 6px 4px 2px;
          flex-wrap: wrap;
        }

        .status-pill {
          font-size: 0.55rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          padding: 2px 8px;
          border-radius: 3px;
          border: 1px solid;
        }

        .status-pill.ok {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.08);
        }

        .status-pill.warn {
          color: var(--status-critical, #ff4444);
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.08);
        }
      </style>

      <div id="content">
        <div class="no-solution">No firing solution</div>
      </div>
    `;
  }

  _updateReticle() {
    if (!this.offsetParent) return; // Skip when hidden (display: none)
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    const targeting = stateManager.getTargeting();
    const lockState = targeting?.lock_state || "none";

    if (lockState !== "locked") {
      content.innerHTML = '<div class="no-solution">No target lock -- designate and lock a target</div>';
      return;
    }

    // Find best solution (prefer railgun)
    const solutions = targeting?.solutions || {};
    let sol = null;
    let weaponId = null;

    for (const [wid, s] of Object.entries(solutions)) {
      if (s.confidence != null) {
        if (!sol || s.confidence > sol.confidence) {
          sol = s;
          weaponId = wid;
        }
      }
    }

    if (!sol) {
      content.innerHTML = '<div class="no-solution">Computing firing solution...</div>';
      return;
    }

    // Extract solution geometry
    const leadYaw = sol.lead_angle?.yaw ?? 0;
    const leadPitch = sol.lead_angle?.pitch ?? 0;
    const confidence = sol.confidence ?? 0;
    const confPct = Math.round(confidence * 100);
    const coneAngle = sol.cone_angle_deg ?? 0;
    const rangM = sol.range ?? sol.range_m ?? 0;
    const tof = sol.time_of_flight ?? 0;
    const inArc = sol.in_arc !== false;
    const inRange = sol.in_range !== false;
    const closing = sol.closing_speed ?? sol.closing_rate ?? 0;

    // Get ship heading for nose indicator
    const nav = stateManager.getNavigation();
    const heading = nav?.heading || {};
    const shipYaw = heading.yaw ?? 0;
    const shipPitch = heading.pitch ?? 0;

    // SVG reticle parameters
    const size = 300;
    const cx = size / 2;
    const cy = size / 2;
    const maxRadius = size / 2 - 20; // leave margin

    // Color based on confidence
    let accentColor, accentDim, confClass;
    if (confPct > 70) {
      accentColor = "#00ff88";
      accentDim = "rgba(0, 255, 136, 0.12)";
      confClass = "high";
    } else if (confPct > 40) {
      accentColor = "#ffaa00";
      accentDim = "rgba(255, 170, 0, 0.10)";
      confClass = "mid";
    } else {
      accentColor = "#ff4444";
      accentDim = "rgba(255, 68, 68, 0.10)";
      confClass = "low";
    }

    // Map lead angle to pixel offset from center.
    // Scale: we treat the reticle as a +/-5 degree viewport.
    // Larger lead angles get clamped to the edge with an arrow indicator.
    const viewAngle = 5; // degrees half-extent
    const scale = maxRadius / viewAngle;

    const rawLeadX = leadYaw * scale;
    const rawLeadY = -leadPitch * scale; // pitch up = SVG up (negative Y)
    const leadDist = Math.sqrt(rawLeadX ** 2 + rawLeadY ** 2);
    const clamped = leadDist > maxRadius;
    const clampFactor = clamped ? maxRadius / leadDist : 1;
    const leadX = rawLeadX * clampFactor;
    const leadY = rawLeadY * clampFactor;

    // Cone radius in reticle pixels
    const conePixels = Math.min(coneAngle * scale, maxRadius * 0.8);

    // Build SVG
    const svg = `
      <svg class="aim-svg" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
        <!-- Background grid -->
        <defs>
          <pattern id="aimGrid" width="30" height="30" patternUnits="userSpaceOnUse">
            <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#1a1a2a" stroke-width="0.5"/>
          </pattern>
        </defs>
        <rect width="${size}" height="${size}" fill="url(#aimGrid)" opacity="0.5"/>

        <!-- Range rings (1-degree intervals) -->
        ${[1, 2, 3, 4].map(deg => {
          const r = deg * scale;
          return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1a1a2a" stroke-width="0.5"/>
                  <text x="${cx + r + 2}" y="${cy - 3}" fill="#333344" font-size="7" font-family="inherit">${deg}deg</text>`;
        }).join("")}

        <!-- Crosshair (ship nose / boresight) -->
        <line x1="${cx - 12}" y1="${cy}" x2="${cx + 12}" y2="${cy}"
              stroke="#555566" stroke-width="1"/>
        <line x1="${cx}" y1="${cy - 12}" x2="${cx}" y2="${cy + 12}"
              stroke="#555566" stroke-width="1"/>
        <circle cx="${cx}" cy="${cy}" r="3" fill="none" stroke="#555566" stroke-width="1"/>

        <!-- Confidence cone at lead point -->
        <circle cx="${cx + leadX}" cy="${cy + leadY}" r="${conePixels}"
                fill="${accentDim}" stroke="${accentColor}" stroke-width="1"
                stroke-dasharray="${conePixels > 20 ? '4,3' : 'none'}"
                opacity="0.7"/>

        <!-- Lead angle marker (computed intercept point) -->
        <circle cx="${cx + leadX}" cy="${cy + leadY}" r="6"
                fill="none" stroke="${accentColor}" stroke-width="2"/>
        <circle cx="${cx + leadX}" cy="${cy + leadY}" r="2"
                fill="${accentColor}"/>

        <!-- Line from boresight to lead point -->
        <line x1="${cx}" y1="${cy}" x2="${cx + leadX}" y2="${cy + leadY}"
              stroke="${accentColor}" stroke-width="1"
              stroke-dasharray="3,4" opacity="0.5"/>

        ${clamped ? `
        <!-- Off-screen indicator arrow -->
        <text x="${cx + leadX}" y="${cy + leadY - 12}"
              fill="${accentColor}" font-size="10" text-anchor="middle"
              font-family="inherit" font-weight="700">OFF-BORE</text>
        ` : ""}

        ${!inArc ? `
        <!-- Arc warning overlay -->
        <rect x="0" y="0" width="${size}" height="${size}"
              fill="rgba(255, 68, 68, 0.05)"/>
        <text x="${cx}" y="${size - 10}"
              fill="#ff4444" font-size="10" text-anchor="middle"
              font-family="inherit" font-weight="700">OUT OF ARC</text>
        ` : ""}

        <!-- Axis labels -->
        <text x="${size - 8}" y="${cy + 3}" fill="#333344" font-size="7"
              text-anchor="end" font-family="inherit">YAW+</text>
        <text x="${cx + 3}" y="14" fill="#333344" font-size="7"
              font-family="inherit">PITCH+</text>
      </svg>
    `;

    // Readout data
    const rangeStr = rangM >= 1000 ? `${(rangM / 1000).toFixed(1)}km` : `${rangM.toFixed(0)}m`;
    const closingStr = Math.abs(closing) >= 1000
      ? `${(closing / 1000).toFixed(1)}km/s`
      : `${closing.toFixed(0)}m/s`;

    content.innerHTML = `
      <div class="aim-container">${svg}</div>
      <div class="status-row">
        <span class="status-pill ${inArc ? 'ok' : 'warn'}">${inArc ? 'IN ARC' : 'OUT OF ARC'}</span>
        <span class="status-pill ${inRange ? 'ok' : 'warn'}">${inRange ? 'IN RANGE' : 'OUT OF RANGE'}</span>
      </div>
      <div class="readout-grid">
        <div class="readout-item">
          <div class="readout-value ${confClass}">${confPct}%</div>
          <div class="readout-label">Confidence</div>
        </div>
        <div class="readout-item">
          <div class="readout-value">${rangeStr}</div>
          <div class="readout-label">Range</div>
        </div>
        <div class="readout-item">
          <div class="readout-value">${tof.toFixed(1)}s</div>
          <div class="readout-label">ToF</div>
        </div>
        <div class="readout-item">
          <div class="readout-value">${leadYaw.toFixed(3)}deg</div>
          <div class="readout-label">Lead Yaw</div>
        </div>
        <div class="readout-item">
          <div class="readout-value">${leadPitch.toFixed(3)}deg</div>
          <div class="readout-label">Lead Pitch</div>
        </div>
        <div class="readout-item">
          <div class="readout-value">${closingStr}</div>
          <div class="readout-label">Closing</div>
        </div>
      </div>
    `;
  }
}

customElements.define("weapon-aiming-panel", WeaponAimingPanel);
export { WeaponAimingPanel };
