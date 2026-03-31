/**
 * Science Analysis Panel
 * Provides controls for science station analysis commands:
 * - Contact selection and deep analysis
 * - Spectral analysis (IR/RCS breakdown)
 * - Mass estimation
 * - Threat assessment
 */

import { stateManager } from "../js/state-manager.js";

class ScienceAnalysisPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._selectedContact = null;
    this._lastResult = null;
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

  async _sendCommand(cmd, args = {}) {
    const wsClient = window._flaxosModules?.wsClient || window.flaxosApp?.wsClient;
    if (wsClient && wsClient.sendShipCommand) {
      try {
        const result = await wsClient.sendShipCommand(cmd, args);
        if (result && result.ok) {
          this._lastResult = result;
          this._showResult(cmd, result);
        }
        return result;
      } catch (err) {
        console.error(`Science command failed: ${cmd}`, err);
        return null;
      }
    }
    return null;
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

        .contact-select {
          width: 100%;
          padding: 6px 8px;
          background: var(--bg-secondary, #12121a);
          color: var(--text-primary, #e0e0e8);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          margin-bottom: 8px;
        }

        .btn-row {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          margin-bottom: 8px;
        }

        .btn {
          padding: 6px 12px;
          background: var(--bg-secondary, #12121a);
          color: var(--text-primary, #e0e0e8);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          cursor: pointer;
          transition: background 0.15s, border-color 0.15s;
        }

        .btn:hover {
          background: var(--bg-tertiary, #1a1a2a);
          border-color: var(--status-info, #00aaff);
        }

        .btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .btn-scan {
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .btn-scan:hover:not(:disabled) {
          background: rgba(0, 170, 255, 0.1);
        }

        .result-panel {
          background: var(--bg-secondary, #12121a);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          padding: 10px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          line-height: 1.5;
          max-height: 300px;
          overflow-y: auto;
          white-space: pre-wrap;
        }

        .result-panel .label {
          color: var(--text-secondary, #888899);
        }

        .result-panel .value {
          color: var(--text-primary, #e0e0e8);
        }

        .result-panel .highlight {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .threat-minimal { color: var(--status-nominal, #00ff88); }
        .threat-low { color: var(--status-nominal, #00ff88); }
        .threat-moderate { color: var(--status-warning, #ffaa00); }
        .threat-high { color: var(--status-critical, #ff4444); }
        .threat-critical { color: var(--status-critical, #ff4444); font-weight: 700; }

        .status-row {
          display: flex;
          justify-content: space-between;
          padding: 3px 0;
        }

        .status-label {
          color: var(--text-secondary, #888899);
        }

        .status-value {
          color: var(--text-primary, #e0e0e8);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .no-contacts {
          color: var(--text-dim, #555566);
          font-style: italic;
          padding: 8px 0;
        }
      </style>

      <div class="section">
        <div class="section-title">Contact Selection</div>
        <select class="contact-select" id="contact-select">
          <option value="">-- Select Contact --</option>
        </select>
        <div class="btn-row">
          <button class="btn" id="btn-analyze" disabled>Analyze</button>
          <button class="btn" id="btn-spectral" disabled>Spectral</button>
          <button class="btn" id="btn-mass" disabled>Est. Mass</button>
          <button class="btn" id="btn-threat" disabled>Threat</button>
        </div>
        <div class="section-title">Active Scans</div>
        <div class="btn-row">
          <button class="btn btn-scan" id="btn-spectral-scan" disabled
            title="Spectral Analysis — identify drive type, ISP, max accel. Effective within 50 km.">
            Spectral Scan
          </button>
          <button class="btn btn-scan" id="btn-composition-scan" disabled
            title="Composition Scan — identify armor, hull class, mass. Effective within 20 km. Requires active radar ping.">
            Composition Scan
          </button>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Analysis Result</div>
        <div class="result-panel" id="result-panel">
          <span class="label">Select a contact and run an analysis command.</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Science Status</div>
        <div id="science-status">
          <div class="status-row">
            <span class="status-label">Sensor Health</span>
            <span class="status-value" id="sensor-health">--</span>
          </div>
          <div class="status-row">
            <span class="status-label">Tracked Contacts</span>
            <span class="status-value" id="tracked-contacts">--</span>
          </div>
        </div>
      </div>
    `;

    // Wire up event handlers
    const select = this.shadowRoot.getElementById("contact-select");
    select.addEventListener("change", (e) => {
      this._selectedContact = e.target.value || null;
      this._updateButtons();
    });

    this.shadowRoot.getElementById("btn-analyze").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("analyze_contact", { contact_id: this._selectedContact });
      }
    });

    this.shadowRoot.getElementById("btn-spectral").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("spectral_analysis", { contact_id: this._selectedContact });
      }
    });

    this.shadowRoot.getElementById("btn-mass").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("estimate_mass", { contact_id: this._selectedContact });
      }
    });

    this.shadowRoot.getElementById("btn-threat").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("assess_threat", { contact_id: this._selectedContact });
      }
    });

    this.shadowRoot.getElementById("btn-spectral-scan").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("science_spectral_analysis", { contact_id: this._selectedContact });
      }
    });

    this.shadowRoot.getElementById("btn-composition-scan").addEventListener("click", () => {
      if (this._selectedContact) {
        this._sendCommand("science_composition_scan", { contact_id: this._selectedContact });
      }
    });
  }

  _updateButtons() {
    const hasContact = !!this._selectedContact;
    this.shadowRoot.getElementById("btn-analyze").disabled = !hasContact;
    this.shadowRoot.getElementById("btn-spectral").disabled = !hasContact;
    this.shadowRoot.getElementById("btn-mass").disabled = !hasContact;
    this.shadowRoot.getElementById("btn-threat").disabled = !hasContact;
    this.shadowRoot.getElementById("btn-spectral-scan").disabled = !hasContact;
    this.shadowRoot.getElementById("btn-composition-scan").disabled = !hasContact;
  }

  _updateDisplay() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    // Update contact list from stateManager convenience method
    this._updateContactList();

    // Update science status from ship telemetry
    // Sensor data lives at ship.sensors (from get_sensor_contacts in telemetry.py)
    const sensors = ship.sensors || {};
    const healthEl = this.shadowRoot.getElementById("sensor-health");
    const contactsEl = this.shadowRoot.getElementById("tracked-contacts");
    if (healthEl) {
      // sensor_health may be on the sensors object or under subsystem_health
      const health = sensors.sensor_health ?? ship.subsystem_health?.sensors;
      healthEl.textContent = health !== undefined
        ? `${(health * 100).toFixed(0)}%`
        : "--";
    }
    if (contactsEl) {
      contactsEl.textContent = sensors.count ?? sensors.contacts?.length ?? "--";
    }
  }

  _updateContactList() {
    const select = this.shadowRoot.getElementById("contact-select");
    if (!select) return;

    // Use stateManager.getContacts() which resolves from ship.sensors.contacts
    const contacts = stateManager.getContacts?.() || [];
    if (!Array.isArray(contacts) || contacts.length === 0) return;

    // Skip innerHTML rebuild if the dropdown is currently focused/open.
    // Rebuilding destroys the native dropdown menu, making it impossible
    // for the user to pick a value.  Instead, do an in-place option sync.
    const isFocused = this.shadowRoot.activeElement === select;

    const currentValue = select.value;
    const desiredIds = contacts.map(c => c.id || c.contact_id).filter(Boolean);

    if (isFocused) {
      // In-place update: only add/remove options, never tear down the DOM
      this._syncSelectOptionsInPlace(select, contacts, currentValue);
      return;
    }

    const options = ['<option value="">-- Select Contact --</option>'];

    for (const c of contacts) {
      const id = c.id || c.contact_id;
      if (!id) continue;
      const dist = c.distance ? `${(c.distance / 1000).toFixed(1)}km` : "?";
      const cls = c.classification || "Unknown";
      const label = `${id} — ${cls} @ ${dist}`;
      options.push(`<option value="${id}">${label}</option>`);
    }

    select.innerHTML = options.join("");
    if (currentValue) {
      select.value = currentValue;
    }
  }

  /**
   * Sync <select> options in-place without destroying the DOM element.
   * Preserves focus and keeps native dropdown menus open while state
   * updates arrive.
   */
  _syncSelectOptionsInPlace(select, contacts, currentValue) {
    const desiredIds = ["", ...contacts.map(c => c.id || c.contact_id).filter(Boolean)];
    const existingIds = Array.from(select.options).map(o => o.value);

    // Only rebuild if the option set actually changed
    if (JSON.stringify(desiredIds) !== JSON.stringify(existingIds)) {
      const options = ['<option value="">-- Select Contact --</option>'];
      for (const c of contacts) {
        const id = c.id || c.contact_id;
        if (!id) continue;
        const dist = c.distance ? `${(c.distance / 1000).toFixed(1)}km` : "?";
        const cls = c.classification || "Unknown";
        const label = `${id} — ${cls} @ ${dist}`;
        options.push(`<option value="${id}">${label}</option>`);
      }
      select.innerHTML = options.join("");
      // Restore user's in-progress selection if it still exists
      if (desiredIds.includes(currentValue)) {
        select.value = currentValue;
      }
    }
    // If options unchanged and focused, leave it alone entirely
  }

  _showResult(command, result) {
    const panel = this.shadowRoot.getElementById("result-panel");
    if (!panel) return;

    let html = "";

    if (command === "analyze_contact") {
      html = this._formatAnalysis(result);
    } else if (command === "spectral_analysis") {
      html = this._formatSpectral(result);
    } else if (command === "estimate_mass") {
      html = this._formatMass(result);
    } else if (command === "assess_threat") {
      html = this._formatThreat(result);
    } else if (command === "science_spectral_analysis") {
      html = this._formatSpectralScan(result);
    } else if (command === "science_composition_scan") {
      html = this._formatCompositionScan(result);
    } else {
      html = `<span class="value">${result.status || JSON.stringify(result)}</span>`;
    }

    panel.innerHTML = html;
  }

  _formatAnalysis(r) {
    const cd = r.contact_data || {};
    const em = r.emissions || {};
    const dist = cd.distance ? `${(cd.distance / 1000).toFixed(1)} km` : "?";
    return `<span class="highlight">CONTACT ANALYSIS: ${r.contact_id}</span>
<span class="label">Classification:</span> <span class="value">${r.classification || "Unknown"}</span>
<span class="label">Distance:</span> <span class="value">${dist}</span>
<span class="label">Confidence:</span> <span class="value">${cd.confidence ? (cd.confidence * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Detection:</span> <span class="value">${cd.detection_method || "?"}</span>
<span class="label">Track Age:</span> <span class="value">${cd.age ? cd.age.toFixed(1) + "s" : "?"}</span>
<span class="label">IR Signature:</span> <span class="value">${em.ir_watts ? this._formatPower(em.ir_watts) : "?"}</span>
<span class="label">RCS:</span> <span class="value">${em.rcs_m2 ? em.rcs_m2.toFixed(1) + " m²" : "?"}</span>
<span class="label">Signature:</span> <span class="value">${em.signature_strength || "?"}</span>
<span class="label">Quality:</span> <span class="value">${r.analysis_quality ? (r.analysis_quality * 100).toFixed(0) + "%" : "?"}</span>`;
  }

  _formatSpectral(r) {
    const sd = r.spectral_data || {};
    const ir = sd.ir_signature || {};
    const rcs = sd.rcs_data || {};
    const drive = sd.drive_inference || {};
    return `<span class="highlight">SPECTRAL ANALYSIS: ${r.contact_id}</span>
<span class="label">Drive Type:</span> <span class="value">${drive.drive_type || "unknown"}</span>
<span class="label">Burn State:</span> <span class="value">${drive.burn_state || "?"}</span>
<span class="label">Est. Thrust:</span> <span class="value">${drive.estimated_thrust_kn ? drive.estimated_thrust_kn + " kN" : "?"}</span>
<span class="label">Total IR:</span> <span class="value">${ir.total_ir ? this._formatPower(ir.total_ir) : "?"}</span>
<span class="label">Plume IR:</span> <span class="value">${ir.plume_ir ? this._formatPower(ir.plume_ir) : "0"}</span>
<span class="label">Radiator/Hull:</span> <span class="value">${ir.radiator_hull_ir ? this._formatPower(ir.radiator_hull_ir) : "?"}</span>
<span class="label">Burning:</span> <span class="value">${ir.is_burning ? "YES" : "no"}</span>
<span class="label">Post-burn Decay:</span> <span class="value">${ir.post_burn_decay ? "YES" : "no"}</span>
<span class="label">RCS:</span> <span class="value">${rcs.effective_rcs ? rcs.effective_rcs.toFixed(1) + " m²" : "?"}</span>
<span class="label">EMCON Detected:</span> <span class="value">${rcs.emcon_detected ? "YES" : "no"}</span>`;
  }

  _formatMass(r) {
    const me = r.mass_estimate || {};
    const di = r.dimension_inference || {};
    return `<span class="highlight">MASS ESTIMATE: ${r.contact_id}</span>
<span class="label">Estimated Mass:</span> <span class="value">${me.estimated_mass ? this._formatMassKg(me.estimated_mass) : "?"}</span>
<span class="label">Confidence:</span> <span class="value">${me.confidence || "?"}</span>
<span class="label">Method:</span> <span class="value">${me.method || "?"}</span>
<span class="label">Range:</span> <span class="value">${me.range_low && me.range_high ? this._formatMassKg(me.range_low) + " — " + this._formatMassKg(me.range_high) : "?"}</span>
<span class="label">Ship Class:</span> <span class="value">${di.ship_class || "?"}</span>
<span class="label">Est. Length:</span> <span class="value">${di.estimated_length ? di.estimated_length.toFixed(0) + " m" : "?"}</span>`;
  }

  _formatThreat(r) {
    const ta = r.threat_assessment || {};
    const cm = ta.countermeasures || {};
    const threatClass = `threat-${ta.overall_threat || "unknown"}`;
    const recs = r.recommendations || [];
    return `<span class="highlight">THREAT ASSESSMENT: ${r.contact_id}</span>
<span class="label">Overall:</span> <span class="${threatClass}">${(ta.overall_threat || "?").toUpperCase()} (${ta.threat_score || 0}/100)</span>
<span class="label">Weapons:</span> <span class="value">${ta.weapons_threat || "?"}</span>
<span class="label">Armor:</span> <span class="value">${ta.armor_threat || "?"}</span>
<span class="label">Mobility:</span> <span class="value">${ta.mobility_threat || "?"}</span>
<span class="label">ECM Active:</span> <span class="value">${cm.ecm_detected ? "YES" : "no"}</span>
<span class="label">EMCON:</span> <span class="value">${cm.emcon_active ? "YES" : "no"}</span>
<span class="label">Notes:</span> <span class="value">${ta.tactical_notes || "none"}</span>
${recs.length > 0 ? '\n<span class="highlight">RECOMMENDATIONS:</span>\n' + recs.map(r => `• ${r}`).join("\n") : ""}`;
  }

  _formatSpectralScan(r) {
    const sd = r.spectral_scan || {};
    const isp = sd.estimated_isp_range || [0, 0];
    const conf = sd.drive_type_confidence ?? 0;
    return `<span class="highlight">SPECTRAL SCAN: ${r.contact_id}</span>
<span class="label">Drive Type:</span> <span class="value">${sd.drive_type || "unknown"}</span>
<span class="label">Drive Confidence:</span> <span class="value">${(conf * 100).toFixed(0)}%</span>
<span class="label">Est. ISP Range:</span> <span class="value">${isp[0].toLocaleString()} — ${isp[1].toLocaleString()} s</span>
<span class="label">Est. Max Accel:</span> <span class="value">${sd.estimated_max_accel ? sd.estimated_max_accel.toFixed(1) + " m/s\u00B2" : "?"}</span>
<span class="label">Scan Quality:</span> <span class="value">${sd.scan_quality ? (sd.scan_quality * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Range:</span> <span class="value">${sd.range_km ? sd.range_km.toFixed(1) + " km" : "?"}</span>`;
  }

  _formatCompositionScan(r) {
    const cd = r.composition_scan || {};
    const conf = cd.class_confidence ?? 0;
    return `<span class="highlight">COMPOSITION SCAN: ${r.contact_id}</span>
<span class="label">Armor Type:</span> <span class="value">${cd.armor_type || "unknown"}</span>
<span class="label">Armor Thickness:</span> <span class="value">${cd.armor_thickness_estimate ? cd.armor_thickness_estimate.toFixed(1) + " mm" : "?"}</span>
<span class="label">Ship Class:</span> <span class="value">${cd.estimated_ship_class || "unknown"}</span>
<span class="label">Class Confidence:</span> <span class="value">${(conf * 100).toFixed(0)}%</span>
<span class="label">Est. Mass:</span> <span class="value">${cd.estimated_mass ? this._formatMassKg(cd.estimated_mass) : "?"}</span>
<span class="label">Scan Quality:</span> <span class="value">${cd.scan_quality ? (cd.scan_quality * 100).toFixed(0) + "%" : "?"}</span>
<span class="label">Range:</span> <span class="value">${cd.range_km ? cd.range_km.toFixed(1) + " km" : "?"}</span>`;
  }

  _formatPower(watts) {
    if (watts >= 1e6) return `${(watts / 1e6).toFixed(1)} MW`;
    if (watts >= 1e3) return `${(watts / 1e3).toFixed(1)} kW`;
    return `${watts.toFixed(0)} W`;
  }

  _formatMassKg(kg) {
    if (kg >= 1000) return `${(kg / 1000).toFixed(1)}t`;
    return `${kg.toFixed(0)} kg`;
  }
}

customElements.define("science-analysis-panel", ScienceAnalysisPanel);
