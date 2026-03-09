/**
 * Navigation Display
 * Shows position, velocity, heading, thrust, autopilot.
 * Tier-aware: renders differently for raw, arcade, and cpu-assist control tiers.
 */

import { stateManager } from "../js/state-manager.js";

class NavigationDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._currentTier = window.controlTier || "arcade";
    this._onTierChange = this._onTierChange.bind(this);
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    window.addEventListener("tier-change", this._onTierChange);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    window.removeEventListener("tier-change", this._onTierChange);
  }

  _onTierChange(event) {
    const newTier = event.detail?.tier || "arcade";
    if (newTier !== this._currentTier) {
      this._currentTier = newTier;
      // Re-render styles since raw tier has a different aesthetic
      this.render();
      this._updateDisplay();
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          padding: 16px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section:last-child {
          margin-bottom: 0;
        }

        .section-title {
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .vector-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 4px 16px;
        }

        .vector-label {
          color: var(--text-dim, #555566);
        }

        .vector-value {
          color: var(--text-primary, #e0e0e0);
          text-align: right;
        }

        .vector-value.positive { color: var(--status-nominal, #00ff88); }
        .vector-value.negative { color: var(--status-critical, #ff4444); }

        .magnitude-row {
          grid-column: span 2;
          display: flex;
          justify-content: space-between;
          padding-top: 8px;
          margin-top: 8px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .magnitude-label {
          color: var(--text-secondary, #888899);
        }

        .magnitude-value {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .heading-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }

        .heading-item {
          text-align: center;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .heading-value {
          font-size: 1.2rem;
          color: var(--text-primary, #e0e0e0);
        }

        .heading-label {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-top: 4px;
        }

        .thrust-container {
          margin-top: 16px;
        }

        .thrust-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .thrust-bar {
          height: 20px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
          position: relative;
        }

        .thrust-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          transition: width 0.2s ease;
        }

        .thrust-text {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.75rem;
          color: var(--text-bright, #ffffff);
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
        }

        .autopilot-section {
          padding: 12px;
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 8px;
          margin-top: 16px;
        }

        .autopilot-section.inactive {
          background: rgba(0, 0, 0, 0.2);
          border-color: var(--border-default, #2a2a3a);
        }

        .autopilot-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .autopilot-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          box-shadow: 0 0 8px var(--status-info, #00aaff);
        }

        .autopilot-indicator.inactive {
          background: var(--status-offline, #555566);
          box-shadow: none;
        }

        .autopilot-mode {
          font-weight: 600;
          color: var(--status-info, #00aaff);
        }

        .autopilot-mode.inactive {
          color: var(--text-dim, #555566);
        }

        .autopilot-details {
          margin-top: 8px;
          font-size: 0.75rem;
          color: var(--text-secondary, #888899);
        }

        .autopilot-detail-row {
          display: flex;
          justify-content: space-between;
          padding: 2px 0;
        }

        .empty-state {
          text-align: center;
          color: var(--text-dim, #555566);
          padding: 24px;
          font-style: italic;
        }

        /* --- Raw tier terminal aesthetic --- */
        :host(.tier-raw) {
          background: #000000;
          color: #00ff88;
          font-family: "Courier New", "Lucida Console", monospace;
          border: 1px solid #00ff8833;
        }

        .raw-container {
          font-family: "Courier New", "Lucida Console", monospace;
          color: #00ff88;
        }

        .raw-velocity-primary {
          font-size: 1.6rem;
          font-weight: 700;
          letter-spacing: 1px;
          color: #00ff88;
          text-shadow: 0 0 6px #00ff8866;
          padding: 4px 0;
        }

        .raw-velocity-grid {
          display: grid;
          grid-template-columns: 40px 1fr;
          gap: 2px 12px;
          margin-bottom: 12px;
        }

        .raw-label {
          color: #00ff8888;
          font-size: 0.75rem;
        }

        .raw-section-header {
          font-size: 0.65rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #00ff8866;
          border-bottom: 1px solid #00ff8833;
          padding-bottom: 4px;
          margin-bottom: 8px;
          margin-top: 16px;
        }

        .raw-readout {
          font-size: 0.8rem;
          color: #00ff88;
          padding: 1px 0;
        }

        .raw-readout-grid {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 2px 16px;
        }

        .raw-readout-value {
          text-align: right;
          color: #00ff88;
        }

        .raw-accel {
          margin-top: 12px;
          padding: 8px;
          background: #00ff8811;
          border: 1px solid #00ff8833;
          border-radius: 4px;
          font-size: 0.9rem;
          font-weight: 600;
          color: #00ff88;
          text-align: center;
        }

        .raw-mag {
          font-size: 1.0rem;
          color: #00aaff;
          text-shadow: 0 0 4px #00aaff44;
          padding: 4px 0;
          text-align: right;
        }

        /* --- CPU Assist tier minimal style --- */
        .autopilot-minimal {
          text-align: center;
        }

        .autopilot-minimal .ap-velocity {
          font-size: 1.8rem;
          font-weight: 700;
          color: var(--status-info, #00aaff);
          margin-bottom: 8px;
        }

        .autopilot-minimal .ap-heading {
          font-size: 1.0rem;
          color: var(--text-secondary, #888899);
          margin-bottom: 16px;
        }

        .autopilot-orders {
          padding: 16px;
          background: rgba(0, 170, 255, 0.15);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 8px;
        }

        .autopilot-orders .ap-order-title {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-info, #00aaff);
          font-weight: 600;
          margin-bottom: 8px;
        }

        .autopilot-orders .ap-order-mode {
          font-size: 1.2rem;
          font-weight: 700;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 8px;
        }

        .ap-progress-bar {
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
          margin-top: 12px;
        }

        .ap-progress-fill {
          height: 100%;
          background: var(--status-info, #00aaff);
          transition: width 0.3s ease;
        }

        .nav-assistance {
          margin-top: 16px;
          padding: 12px;
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          border-radius: 8px;
        }

        .nav-assistance.inactive {
          background: rgba(0, 0, 0, 0.2);
          border-color: var(--border-default, #2a2a3a);
        }

        .suggestion-item {
          margin-top: 8px;
          padding: 8px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 4px;
          font-size: 0.75rem;
        }

        .suggestion-type {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .suggestion-text {
          color: var(--text-secondary, #888899);
          margin-top: 4px;
        }
      </style>

      <div id="content">
        <div class="empty-state">Waiting for navigation data...</div>
      </div>
    `;

    // Apply tier class to host element for CSS scoping
    this.classList.remove("tier-raw", "tier-arcade", "tier-cpu-assist");
    this.classList.add(`tier-${this._currentTier}`);
  }

  /**
   * Gather common nav/ship data then dispatch to the tier-specific renderer.
   */
  _updateDisplay() {
    const nav = stateManager.getNavigation();
    const ship = stateManager.getShipState();
    const content = this.shadowRoot.getElementById("content");

    if (!ship || Object.keys(ship).length === 0) {
      content.innerHTML = '<div class="empty-state">Waiting for navigation data...</div>';
      return;
    }

    const position = nav.position || [0, 0, 0];
    const velocity = nav.velocity || [0, 0, 0];
    const heading = nav.heading || { pitch: 0, yaw: 0 };
    const thrust = (nav.thrust ?? 0) * 100;
    const autopilot = nav.autopilot || ship.autopilot || null;

    // Navigation awareness data
    const navAwareness = ship.navigation || {};
    const velocityHeading = navAwareness.velocity_heading || { pitch: 0, yaw: 0 };
    const driftAngle = navAwareness.drift_angle || 0;
    const velMagnitude = navAwareness.velocity_magnitude || this._magnitude(velocity);

    // Propulsion G-force data
    const propulsion = ship.systems?.propulsion || {};
    const thrustG = propulsion.thrust_g || 0;
    const maxThrustG = propulsion.max_thrust_g || 0;

    // Angular velocity from RCS or nav state
    const rcs = ship.systems?.rcs || {};
    const angularVelocity = rcs.angular_velocity || nav.angular_velocity || { pitch: 0, yaw: 0, roll: 0 };

    // Orientation (full pitch/yaw/roll)
    const orientation = ship.orientation || heading;
    const roll = orientation.roll ?? heading.roll ?? 0;

    const data = {
      position, velocity, heading, thrust, autopilot,
      navAwareness, velocityHeading, driftAngle, velMagnitude,
      thrustG, maxThrustG, angularVelocity, orientation, roll, ship
    };

    switch (this._currentTier) {
      case "raw":
        content.innerHTML = this._renderRaw(data);
        break;
      case "cpu-assist":
        content.innerHTML = this._renderCpuAssistTier(data);
        break;
      case "arcade":
      default:
        content.innerHTML = this._renderArcade(data);
        break;
    }
  }

  // ---------- Arcade tier (current default behavior) ----------

  _renderArcade(data) {
    const { position, velocity, heading, thrust, autopilot,
            navAwareness, velocityHeading, driftAngle, velMagnitude,
            thrustG, maxThrustG, ship } = data;

    return `
      <div class="section">
        <div class="section-title">Position</div>
        <div class="vector-grid">
          <span class="vector-label">X:</span>
          <span class="vector-value ${position[0] >= 0 ? 'positive' : 'negative'}">${this._formatDistance(position[0])}</span>
          <span class="vector-label">Y:</span>
          <span class="vector-value ${position[1] >= 0 ? 'positive' : 'negative'}">${this._formatDistance(position[1])}</span>
          <span class="vector-label">Z:</span>
          <span class="vector-value ${position[2] >= 0 ? 'positive' : 'negative'}">${this._formatDistance(position[2])}</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Velocity</div>
        <div class="vector-grid">
          <span class="vector-label">VX:</span>
          <span class="vector-value ${velocity[0] >= 0 ? 'positive' : 'negative'}">${this._formatVelocity(velocity[0])}</span>
          <span class="vector-label">VY:</span>
          <span class="vector-value ${velocity[1] >= 0 ? 'positive' : 'negative'}">${this._formatVelocity(velocity[1])}</span>
          <span class="vector-label">VZ:</span>
          <span class="vector-value ${velocity[2] >= 0 ? 'positive' : 'negative'}">${this._formatVelocity(velocity[2])}</span>
          <div class="magnitude-row">
            <span class="magnitude-label">MAG:</span>
            <span class="magnitude-value">${this._formatVelocity(velMagnitude)}</span>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Heading</div>
        <div class="heading-grid">
          <div class="heading-item">
            <div class="heading-value">${this._formatAngle(heading.pitch || 0)}°</div>
            <div class="heading-label">Pitch</div>
          </div>
          <div class="heading-item">
            <div class="heading-value">${this._formatAngle(heading.yaw || 0)}°</div>
            <div class="heading-label">Yaw</div>
          </div>
        </div>
      </div>

      <div class="thrust-container">
        <div class="thrust-header">
          <span class="section-title">Thrust</span>
        </div>
        <div class="thrust-bar">
          <div class="thrust-fill" style="width: ${thrust}%"></div>
          <span class="thrust-text">${thrust.toFixed(0)}%</span>
        </div>
        ${thrustG > 0 ? `
          <div style="margin-top: 4px; font-size: 0.7rem; color: var(--status-info, #00aaff);">
            ${thrustG.toFixed(2)} G ${maxThrustG > 0 ? `/ ${maxThrustG.toFixed(1)} G max` : ''}
          </div>
        ` : ''}
      </div>

      ${this._renderNavigationAwareness(navAwareness, velocityHeading, driftAngle)}

      ${this._renderNavAssistance(ship)}

      ${this._renderAutopilot(autopilot)}
    `;
  }

  // ---------- Raw tier: terminal-style, velocity-dominant ----------

  _renderRaw(data) {
    const { position, velocity, heading, thrust, velMagnitude,
            thrustG, angularVelocity, orientation, roll } = data;

    // Acceleration in m/s^2 (thrust_g * 9.81)
    const accelMs2 = thrustG * 9.81;

    return `
      <div class="raw-container">
        <div class="raw-section-header">VELOCITY</div>
        <div class="raw-velocity-grid">
          <span class="raw-label">VX</span>
          <span class="raw-velocity-primary">${this._formatVelocityRaw(velocity[0])}</span>
          <span class="raw-label">VY</span>
          <span class="raw-velocity-primary">${this._formatVelocityRaw(velocity[1])}</span>
          <span class="raw-label">VZ</span>
          <span class="raw-velocity-primary">${this._formatVelocityRaw(velocity[2])}</span>
        </div>
        <div class="raw-mag">MAG ${this._formatVelocityRaw(velMagnitude)}</div>

        <div class="raw-section-header">ORIENTATION</div>
        <div class="raw-readout-grid">
          <span class="raw-label">PIT</span>
          <span class="raw-readout-value">${this._formatAngle(heading.pitch || orientation.pitch || 0)}°</span>
          <span class="raw-label">YAW</span>
          <span class="raw-readout-value">${this._formatAngle(heading.yaw || orientation.yaw || 0)}°</span>
          <span class="raw-label">ROL</span>
          <span class="raw-readout-value">${this._formatAngle(roll)}°</span>
        </div>

        <div class="raw-section-header">ANGULAR RATE</div>
        <div class="raw-readout-grid">
          <span class="raw-label">P</span>
          <span class="raw-readout-value">${this._formatAngularRate(angularVelocity.pitch)}°/s</span>
          <span class="raw-label">Y</span>
          <span class="raw-readout-value">${this._formatAngularRate(angularVelocity.yaw)}°/s</span>
          <span class="raw-label">R</span>
          <span class="raw-readout-value">${this._formatAngularRate(angularVelocity.roll)}°/s</span>
        </div>

        <div class="raw-section-header">POSITION (m)</div>
        <div class="raw-readout-grid">
          <span class="raw-label">X</span>
          <span class="raw-readout-value">${this._formatDistanceRaw(position[0])}</span>
          <span class="raw-label">Y</span>
          <span class="raw-readout-value">${this._formatDistanceRaw(position[1])}</span>
          <span class="raw-label">Z</span>
          <span class="raw-readout-value">${this._formatDistanceRaw(position[2])}</span>
        </div>

        <div class="raw-accel">ACCEL: ${accelMs2.toFixed(2)} m/s² FWD</div>
      </div>
    `;
  }

  // ---------- CPU Assist tier: minimal with prominent AP status ----------

  _renderCpuAssistTier(data) {
    const { heading, velMagnitude, autopilot } = data;

    const isActive = autopilot && autopilot.mode && autopilot.mode !== "off" && autopilot.mode !== "manual";
    const mode = autopilot?.mode || "MANUAL";
    const target = autopilot?.target || autopilot?.target_id || null;
    const phase = autopilot?.phase || null;
    const range = autopilot?.range ?? autopilot?.distance ?? null;
    const closingSpeed = autopilot?.closingSpeed ?? null;
    const etaSeconds = this._calculateEtaSeconds(range, closingSpeed, autopilot?.eta ?? null);
    const progress = autopilot?.progress ?? null;

    return `
      <div class="autopilot-minimal">
        <div class="ap-velocity">${this._formatVelocity(velMagnitude)}</div>
        <div class="ap-heading">HDG ${this._formatAngle(heading.pitch || 0)}° / ${this._formatAngle(heading.yaw || 0)}°</div>
      </div>

      <div class="autopilot-orders">
        <div class="ap-order-title">Autopilot Orders</div>
        ${isActive ? `
          <div class="ap-order-mode">${mode.toUpperCase()}${target ? ` - ${target}` : ''}</div>
          <div class="autopilot-details">
            ${phase ? `
              <div class="autopilot-detail-row">
                <span>Phase:</span>
                <span>${phase.toUpperCase()}</span>
              </div>
            ` : ''}
            ${range !== null ? `
              <div class="autopilot-detail-row">
                <span>Range:</span>
                <span>${this._formatRangeDistance(range)}</span>
              </div>
            ` : ''}
            ${etaSeconds !== null ? `
              <div class="autopilot-detail-row">
                <span>ETA:</span>
                <span>${this._formatDuration(etaSeconds)}</span>
              </div>
            ` : ''}
            ${closingSpeed !== null ? `
              <div class="autopilot-detail-row">
                <span>Closing:</span>
                <span>${this._formatVelocity(closingSpeed)}</span>
              </div>
            ` : ''}
          </div>
          ${progress !== null ? `
            <div class="ap-progress-bar">
              <div class="ap-progress-fill" style="width: ${(progress * 100).toFixed(1)}%"></div>
            </div>
          ` : ''}
        ` : `
          <div class="ap-order-mode" style="color: var(--text-dim, #555566);">NO ORDERS</div>
          <div style="font-size: 0.75rem; color: var(--text-dim, #555566); margin-top: 8px;">
            Autopilot standing by
          </div>
        `}
      </div>
    `;
  }

  _renderNavAssistance(ship) {
    const navSystem = ship?.systems?.navigation || {};
    const navAssistance = navSystem.nav_assistance || {};
    
    if (!navAssistance.nav_computer_online) {
      return '';
    }

    const suggestions = navAssistance.suggestions || [];
    const hasSuggestions = suggestions.length > 0;

    return `
      <div class="nav-assistance ${hasSuggestions ? '' : 'inactive'}">
        <div class="section-title">Nav Computer Assistance</div>
        ${hasSuggestions ? `
          ${suggestions.map(s => `
            <div class="suggestion-item">
              <div class="suggestion-type">${s.type.toUpperCase()}</div>
              <div class="suggestion-text">${s.text}</div>
            </div>
          `).join('')}
        ` : `
          <div style="font-size: 0.75rem; color: var(--text-dim, #555566);">
            Nav computer online - calculations available
          </div>
        `}
      </div>
    `;
  }

  _renderNavigationAwareness(navAwareness, velocityHeading, driftAngle) {
    if (!navAwareness || Object.keys(navAwareness).length === 0) {
      return '';
    }

    const driftClass = Math.abs(driftAngle) < 5 ? 'positive' : Math.abs(driftAngle) < 30 ? 'warning' : 'negative';
    const driftText = Math.abs(driftAngle) < 1 ? 'ON-AXIS' : `${driftAngle.toFixed(1)}° DRIFT`;

    return `
      <div class="section">
        <div class="section-title">Navigation Awareness</div>
        <div class="vector-grid">
          <span class="vector-label">Velocity Heading:</span>
          <span class="vector-value">${this._formatAngle(velocityHeading.pitch || 0)}° / ${this._formatAngle(velocityHeading.yaw || 0)}°</span>
          <span class="vector-label">Drift Angle:</span>
          <span class="vector-value ${driftClass}">${driftText}</span>
        </div>
      </div>
    `;
  }

  _renderAutopilot(autopilot) {
    const isActive = autopilot && autopilot.mode && autopilot.mode !== "off" && autopilot.mode !== "manual";
    const mode = autopilot?.mode || "MANUAL";
    const target = autopilot?.target || autopilot?.target_id || null;
    const phase = autopilot?.phase || null;
    const range = autopilot?.range ?? autopilot?.distance ?? null;
    const closingSpeed = autopilot?.closingSpeed ?? null;
    const etaSeconds = this._calculateEtaSeconds(range, closingSpeed, autopilot?.eta ?? null);

    return `
      <div class="autopilot-section ${isActive ? '' : 'inactive'}">
        <div class="autopilot-header">
          <div class="autopilot-indicator ${isActive ? '' : 'inactive'}"></div>
          <span class="autopilot-mode ${isActive ? '' : 'inactive'}">
            AUTOPILOT: ${mode.toUpperCase()}${target ? ` ${target}` : ''}
          </span>
        </div>
        ${isActive ? `
          <div class="autopilot-details">
            ${phase ? `
              <div class="autopilot-detail-row">
                <span>Phase:</span>
                <span>${phase.toUpperCase()}</span>
              </div>
            ` : ''}
            ${range !== null ? `
              <div class="autopilot-detail-row">
                <span>Range:</span>
                <span>${this._formatRangeDistance(range)}</span>
              </div>
            ` : ''}
            ${etaSeconds !== null ? `
              <div class="autopilot-detail-row">
                <span>ETA:</span>
                <span>${this._formatDuration(etaSeconds)}</span>
              </div>
            ` : ''}
            ${closingSpeed !== null ? `
              <div class="autopilot-detail-row">
                <span>Closing:</span>
                <span>${this._formatVelocity(closingSpeed)}</span>
              </div>
            ` : ''}
          </div>
        ` : ''}
      </div>
    `;
  }

  _magnitude(vec) {
    return Math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2);
  }

  _formatDistance(meters) {
    const abs = Math.abs(meters);
    const sign = meters >= 0 ? "+" : "-";
    if (abs >= 1000000) {
      return `${sign}${(abs / 1000).toFixed(1)} km`;
    }
    if (abs >= 1000) {
      return `${sign}${(abs / 1000).toFixed(2)} km`;
    }
    return `${sign}${abs.toFixed(1)} m`;
  }

  _formatRangeDistance(meters) {
    const abs = Math.abs(meters);
    if (abs >= 1000000) {
      return `${(abs / 1000).toFixed(1)} km`;
    }
    if (abs >= 1000) {
      return `${(abs / 1000).toFixed(2)} km`;
    }
    return `${abs.toFixed(1)} m`;
  }

  _formatVelocity(mps) {
    const abs = Math.abs(mps);
    const sign = mps >= 0 ? "+" : "-";
    if (abs >= 1000) {
      return `${sign}${(abs / 1000).toFixed(2)} km/s`;
    }
    return `${sign}${abs.toFixed(1)} m/s`;
  }

  _formatAngle(degrees) {
    const sign = degrees >= 0 ? "+" : "";
    return `${sign}${degrees.toFixed(1)}`;
  }

  _calculateEtaSeconds(range, closingSpeed, fallbackEta) {
    if (typeof fallbackEta === "number" && Number.isFinite(fallbackEta)) {
      return fallbackEta;
    }
    if (typeof range !== "number" || !Number.isFinite(range)) {
      return null;
    }
    if (typeof closingSpeed !== "number" || !Number.isFinite(closingSpeed)) {
      return null;
    }
    if (closingSpeed <= 0) {
      return null;
    }
    return range / closingSpeed;
  }

  /**
   * Format velocity for raw tier: always m/s, signed, fixed-width feel.
   */
  _formatVelocityRaw(mps) {
    const sign = mps >= 0 ? "+" : "-";
    const abs = Math.abs(mps);
    return `${sign}${abs.toFixed(1)} m/s`;
  }

  /**
   * Format distance for raw tier: always meters, no auto-km conversion.
   */
  _formatDistanceRaw(meters) {
    const sign = meters >= 0 ? "+" : "-";
    return `${sign}${Math.abs(meters).toFixed(1)}`;
  }

  /**
   * Format angular rate in degrees/sec for raw tier display.
   */
  _formatAngularRate(degPerSec) {
    const val = degPerSec || 0;
    const sign = val >= 0 ? "+" : "";
    return `${sign}${val.toFixed(2)}`;
  }

  _formatDuration(seconds) {
    const totalSeconds = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes.toString().padStart(2, "0")}m ${secs.toString().padStart(2, "0")}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
    }
    return `${secs}s`;
  }
}

customElements.define("navigation-display", NavigationDisplay);
export { NavigationDisplay };
