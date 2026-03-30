/**
 * ECCM Control Panel
 * Counter-countermeasures controls for the tactical view.
 *
 * Modes (mutually exclusive primary modes):
 *   - Frequency Hop: reduces noise jamming 60-80%, costs extra sensor power
 *   - Burn-Through: brute-force radar power boost, massive heat + reveals own position
 *   - Off: no active ECCM mode
 *
 * Toggles (independent of primary mode):
 *   - Multi-Spectral: cross-reference IR/radar/lidar to filter chaff and flares
 *   - Home-on-Jam: use enemy jammer emissions as bearing source
 *
 * Commands:
 *   eccm_frequency_hop, eccm_burn_through, eccm_off,
 *   eccm_multispectral, eccm_home_on_jam, analyze_jamming, eccm_status
 *
 * Telemetry path: ship.systems.sensors.eccm
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class ECCMControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._analysisResult = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
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
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 12px;
        }

        .section {
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-info, #00aaff);
          margin-bottom: 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        /* ECCM mode indicator — mirrors ECM panel pattern */
        .eccm-mode {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 10px;
          margin-bottom: 12px;
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .eccm-mode.standby {
          background: rgba(85, 85, 102, 0.15);
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .eccm-mode.active {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .eccm-mode.burn-through {
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .mode-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: currentColor;
        }

        .eccm-mode.active .mode-dot,
        .eccm-mode.burn-through .mode-dot {
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* Burn-through warning banner */
        .burn-warning {
          display: none;
          background: rgba(255, 68, 68, 0.15);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 4px;
          padding: 6px 10px;
          margin-bottom: 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--status-critical, #ff4444);
          text-align: center;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          animation: warn-flash 2s ease-in-out infinite;
        }

        .burn-warning.visible {
          display: block;
        }

        @keyframes warn-flash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        /* Mode buttons grid */
        .controls-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-top: 8px;
        }

        .eccm-btn {
          background: rgba(0, 170, 255, 0.1);
          border: 1px solid rgba(0, 170, 255, 0.3);
          border-radius: 4px;
          color: var(--status-info, #00aaff);
          padding: 8px 10px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          cursor: pointer;
          text-transform: uppercase;
          transition: all 0.15s ease;
          text-align: center;
          min-height: 36px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 2px;
        }

        .eccm-btn:hover {
          background: rgba(0, 170, 255, 0.2);
          border-color: var(--status-info, #00aaff);
        }

        .eccm-btn.active {
          background: rgba(0, 255, 136, 0.15);
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .eccm-btn.burn-active {
          background: rgba(255, 68, 68, 0.15);
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .eccm-btn.full-width {
          grid-column: 1 / -1;
        }

        .btn-hint {
          font-size: 0.6rem;
          opacity: 0.7;
        }

        /* Status readout rows */
        .status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 0;
          font-size: 0.75rem;
        }

        .status-label {
          color: var(--text-secondary, #888899);
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
        }

        .status-value.active {
          color: var(--status-nominal, #00ff88);
        }

        .status-value.warning {
          color: var(--status-warning, #ffaa00);
        }

        .status-value.critical {
          color: var(--status-critical, #ff4444);
        }

        /* Analyze jamming section */
        .analyze-row {
          display: flex;
          gap: 6px;
          align-items: center;
          margin-top: 8px;
        }

        .analyze-select {
          flex: 1;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          padding: 6px 8px;
        }

        .analyze-select option {
          background: #1a1a2e;
        }

        .analysis-result {
          margin-top: 8px;
          padding: 8px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .analysis-result.no-ecm {
          background: rgba(85, 85, 102, 0.15);
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .analysis-result.threats {
          background: rgba(255, 170, 0, 0.1);
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--text-primary, #e0e0e0);
        }

        .analysis-result .threat-line {
          padding: 2px 0;
        }

        .analysis-result .recommendation {
          margin-top: 6px;
          padding-top: 6px;
          border-top: 1px solid rgba(255, 170, 0, 0.2);
          color: var(--status-warning, #ffaa00);
          font-weight: 600;
          text-transform: uppercase;
        }

        .no-eccm {
          color: var(--text-dim, #555566);
          font-style: italic;
          text-align: center;
          padding: 20px 10px;
          font-size: 0.75rem;
        }
      </style>

      <div id="eccm-content">
        <div class="no-eccm">ECCM system not available</div>
      </div>
    `;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    // ECCM state is a top-level telemetry field (added alongside ecm, comms, etc.)
    const eccm = ship?.eccm;
    const container = this.shadowRoot.getElementById("eccm-content");

    if (!eccm || !container) {
      if (container) {
        container.innerHTML = '<div class="no-eccm">ECCM system not available</div>';
      }
      return;
    }

    // Check if the analyze-target dropdown is currently focused/open.
    // Rebuilding innerHTML while a <select> is open destroys the native
    // dropdown menu, making it impossible to pick a value.  When the
    // dropdown is open, skip the full rebuild and do a targeted in-place
    // update of just the select options and status values.
    const analyzeSelect = this.shadowRoot.getElementById("analyze-target");
    const dropdownOpen = analyzeSelect &&
      this.shadowRoot.activeElement === analyzeSelect;

    if (dropdownOpen) {
      this._updateInPlace(eccm);
      return;
    }

    const mode = eccm.mode || "off";
    const isBurnThrough = mode === "burn_through";
    const isFreqHop = mode === "frequency_hop";
    const isOff = mode === "off";

    // Mode indicator class
    let modeClass = "standby";
    if (isBurnThrough) modeClass = "burn-through";
    else if (isFreqHop || eccm.multispectral_active || eccm.hoj_active) modeClass = "active";

    const statusText = eccm.status || "standby";

    // Build contacts dropdown for analyze_jamming
    const contacts = stateManager.getContacts?.() || [];
    const contactOptions = contacts.map(c => {
      const label = c.name || c.classification || c.contact_id || c.id;
      const id = c.contact_id || c.id;
      return `<option value="${id}">${label}</option>`;
    }).join("");

    // Analysis result HTML
    let analysisHTML = this._buildAnalysisHTML();

    container.innerHTML = `
      <!-- ECCM Mode Indicator -->
      <div class="eccm-mode ${modeClass}">
        <div class="mode-dot"></div>
        <span>${statusText}</span>
      </div>

      <!-- Burn-through warning: high heat + increased emission signature -->
      <div class="burn-warning ${isBurnThrough ? 'visible' : ''}">
        Burn-through active — high heat + ${eccm.burn_through_emission_mult || 6}x emission signature
      </div>

      <!-- Primary Mode (mutually exclusive) -->
      <div class="section">
        <div class="section-title">ECCM Mode</div>
        <div class="controls-grid">
          <button class="eccm-btn ${isFreqHop ? 'active' : ''}"
                  id="btn-freq-hop"
                  title="Rapidly change radar frequency to decorrelate from noise jamming. 60-80% jam reduction.">
            FREQ HOP
            <span class="btn-hint">jam -${isFreqHop && eccm.freq_hop_jam_reduction ? Math.round(eccm.freq_hop_jam_reduction * 100) : '70'}%</span>
          </button>
          <button class="eccm-btn ${isBurnThrough ? 'burn-active' : ''}"
                  id="btn-burn-through"
                  title="Brute-force radar power increase. Massive heat generation and reveals own position.">
            BURN-THRU
            <span class="btn-hint">${isBurnThrough && eccm.burn_through_radar_mult ? eccm.burn_through_radar_mult + 'x' : '4x'} radar</span>
          </button>
          <button class="eccm-btn full-width ${isOff && !eccm.multispectral_active && !eccm.hoj_active ? 'active' : ''}"
                  id="btn-eccm-off"
                  title="Deactivate ECCM mode (frequency hop or burn-through)">
            ECCM OFF
          </button>
        </div>
      </div>

      <!-- Toggle Modes (independent of primary mode) -->
      <div class="section">
        <div class="section-title">Sensor Modes</div>
        <div class="controls-grid">
          <button class="eccm-btn ${eccm.multispectral_active ? 'active' : ''}"
                  id="btn-multispectral"
                  title="Cross-reference IR, radar, lidar to filter chaff/flares. Requires 2+ sensor types.">
            MULTI-SPEC
            <span class="btn-hint">chaff/flare filter</span>
          </button>
          <button class="eccm-btn ${eccm.hoj_active ? 'active' : ''}"
                  id="btn-hoj"
                  title="Use enemy jammer emissions as bearing source. Bearing only, no range.">
            HOME-ON-JAM
            <span class="btn-hint">bearing only</span>
          </button>
        </div>
      </div>

      <!-- Analyze Jamming -->
      <div class="section">
        <div class="section-title">Jamming Analysis</div>
        <div class="analyze-row">
          <select class="analyze-select" id="analyze-target">
            <option value="">-- select target --</option>
            ${contactOptions}
          </select>
          <button class="eccm-btn" id="btn-analyze" title="Analyze target ECM emissions and recommend countermeasure">
            ANALYZE
          </button>
        </div>
        ${analysisHTML}
      </div>

      <!-- Status Readout -->
      <div class="section">
        <div class="section-title">Status</div>
        <div class="status-row">
          <span class="status-label">Mode</span>
          <span class="status-value ${isBurnThrough ? 'critical' : isFreqHop ? 'active' : ''}" id="status-mode">${mode.replace(/_/g, "-").toUpperCase()}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Sensor Health</span>
          <span class="status-value ${eccm.sensor_health < 0.5 ? 'critical' : eccm.sensor_health < 0.8 ? 'warning' : ''}" id="status-sensor-health">${Math.round((eccm.sensor_health || 0) * 100)}%</span>
        </div>
        <div class="status-row">
          <span class="status-label">Power Draw</span>
          <span class="status-value ${eccm.power_multiplier > 2 ? 'warning' : ''}" id="status-power">${eccm.power_multiplier || 1.0}x</span>
        </div>
        ${isBurnThrough ? `
        <div class="status-row">
          <span class="status-label">Emission Sig</span>
          <span class="status-value critical">${eccm.burn_through_emission_mult || 6}x</span>
        </div>
        ` : ''}
        <div class="status-row">
          <span class="status-label">Multi-Spectral</span>
          <span class="status-value ${eccm.multispectral_active ? 'active' : ''}" id="status-multispec">${eccm.multispectral_active ? 'ACTIVE' : 'OFF'}</span>
        </div>
        <div class="status-row">
          <span class="status-label">Home-on-Jam</span>
          <span class="status-value ${eccm.hoj_active ? 'active' : ''}" id="status-hoj">${eccm.hoj_active ? 'ACTIVE' : 'OFF'}</span>
        </div>
      </div>
    `;

    this._bindButtons();
  }

  /**
   * Build the analysis result HTML fragment from cached _analysisResult.
   * Extracted to avoid duplicating this logic across full rebuild and
   * in-place update paths.
   */
  _buildAnalysisHTML() {
    if (!this._analysisResult) return "";

    const ar = this._analysisResult;
    if (!ar.ecm_detected) {
      return `
        <div class="analysis-result no-ecm">
          No ECM emissions detected
        </div>`;
    }

    const threatLines = (ar.threats || []).map(t => {
      const type = (t.type || "unknown").replace(/_/g, " ");
      const severity = t.severity ? ` [${t.severity}]` : "";
      return `<div class="threat-line">${type}${severity}</div>`;
    }).join("");

    const recLabel = (ar.recommendation || "none").replace(/_/g, " ");
    return `
      <div class="analysis-result threats">
        ${threatLines}
        <div class="recommendation">Recommend: ${recLabel}</div>
      </div>`;
  }

  /**
   * Targeted in-place update when the analyze-target dropdown is open.
   * Updates status readout values and syncs the select's option list
   * without destroying the DOM, so the native dropdown stays open.
   */
  _updateInPlace(eccm) {
    // Sync the analyze-target <select> options without rebuilding
    const select = this.shadowRoot.getElementById("analyze-target");
    if (select) {
      const contacts = stateManager.getContacts?.() || [];
      const currentValue = select.value;
      const desiredIds = ["", ...contacts.map(c => c.contact_id || c.id).filter(Boolean)];
      const existingIds = Array.from(select.options).map(o => o.value);

      // Only touch options if the contact set changed
      if (JSON.stringify(desiredIds) !== JSON.stringify(existingIds)) {
        const optionsHTML = '<option value="">-- select target --</option>' +
          contacts.map(c => {
            const label = c.name || c.classification || c.contact_id || c.id;
            const id = c.contact_id || c.id;
            return `<option value="${id}">${label}</option>`;
          }).join("");
        select.innerHTML = optionsHTML;
        if (desiredIds.includes(currentValue)) {
          select.value = currentValue;
        }
      }
    }

    // Update status text values in-place (these are safe -- no focus issues)
    const mode = eccm.mode || "off";
    const modeEl = this.shadowRoot.getElementById("status-mode");
    if (modeEl) modeEl.textContent = mode.replace(/_/g, "-").toUpperCase();

    const healthEl = this.shadowRoot.getElementById("status-sensor-health");
    if (healthEl) healthEl.textContent = `${Math.round((eccm.sensor_health || 0) * 100)}%`;

    const powerEl = this.shadowRoot.getElementById("status-power");
    if (powerEl) powerEl.textContent = `${eccm.power_multiplier || 1.0}x`;

    const multispecEl = this.shadowRoot.getElementById("status-multispec");
    if (multispecEl) multispecEl.textContent = eccm.multispectral_active ? "ACTIVE" : "OFF";

    const hojEl = this.shadowRoot.getElementById("status-hoj");
    if (hojEl) hojEl.textContent = eccm.hoj_active ? "ACTIVE" : "OFF";
  }

  _bindButtons() {
    const bind = (id, handler) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.addEventListener("click", handler);
    };

    bind("btn-freq-hop", () => {
      wsClient.sendShipCommand("eccm_frequency_hop", {}).catch(e =>
        console.warn("ECCM freq hop failed:", e.message));
    });

    bind("btn-burn-through", () => {
      wsClient.sendShipCommand("eccm_burn_through", {}).catch(e =>
        console.warn("ECCM burn-through failed:", e.message));
    });

    bind("btn-eccm-off", () => {
      wsClient.sendShipCommand("eccm_off", {}).catch(e =>
        console.warn("ECCM off failed:", e.message));
    });

    bind("btn-multispectral", () => {
      wsClient.sendShipCommand("eccm_multispectral", {}).catch(e =>
        console.warn("ECCM multispectral failed:", e.message));
    });

    bind("btn-hoj", () => {
      wsClient.sendShipCommand("eccm_home_on_jam", {}).catch(e =>
        console.warn("ECCM home-on-jam failed:", e.message));
    });

    bind("btn-analyze", async () => {
      const select = this.shadowRoot.getElementById("analyze-target");
      const contactId = select?.value;
      if (!contactId) return;

      try {
        const result = await wsClient.sendShipCommand("analyze_jamming", {
          contact_id: contactId,
        });
        this._analysisResult = result;
        // Re-render to show result (next state update will also refresh)
        this._updateDisplay();
      } catch (e) {
        console.warn("Analyze jamming failed:", e.message);
      }
    });
  }
}

customElements.define("eccm-control-panel", ECCMControlPanel);
export default ECCMControlPanel;
