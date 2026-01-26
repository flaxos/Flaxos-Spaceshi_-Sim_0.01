/**
 * Navigation Display
 * Shows position, velocity, heading, thrust, autopilot
 */

import { stateManager } from "../js/state-manager.js";

class NavigationDisplay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
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
  }

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

    // Get navigation awareness data
    const navAwareness = ship.navigation || {};
    const velocityHeading = navAwareness.velocity_heading || { pitch: 0, yaw: 0 };
    const driftAngle = navAwareness.drift_angle || 0;
    const velMagnitude = navAwareness.velocity_magnitude || this._magnitude(velocity);
    
    // Get propulsion G-force data
    const propulsion = ship.systems?.propulsion || {};
    const thrustG = propulsion.thrust_g || 0;
    const maxThrustG = propulsion.max_thrust_g || 0;

    content.innerHTML = `
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
    const range = autopilot?.range || null;

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
                <span>${this._formatDistance(range)}</span>
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
}

customElements.define("navigation-display", NavigationDisplay);
export { NavigationDisplay };
