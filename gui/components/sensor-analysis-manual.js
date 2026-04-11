/**
 * Sensor Analysis Panel (MANUAL / RAW tiers)
 *
 * Data-dense raw sensor diagnostics for the currently selected contact.
 * MANUAL players interpret IR signatures, SNR calculations, detection
 * probability, and drive state estimates themselves -- no automation.
 *
 * Data source: stateManager "sensors" → contacts[]
 * Contact selection: listens for "contact-selected" CustomEvent on document
 * Update rate: throttled to 5 Hz (200 ms minimum between renders)
 */

import { stateManager } from "../js/state-manager.js";

// IR signature thresholds for mass classification
const MASS_THRESHOLDS = [
  { max: 1e3, label: "DEBRIS/MISSILE" },
  { max: 1e5, label: "SMALL CRAFT" },
  { max: 1e7, label: "CORVETTE/FRIGATE" },
  { max: Infinity, label: "CAPITAL SHIP" },
];

// IR signature thresholds for drive state estimation
const DRIVE_THRESHOLDS = {
  high: 1e6, // > 1 MW = active burn
  medium: 1e4, // > 10 kW = maneuvering
};

/**
 * Classify contact mass from IR signature magnitude.
 * @param {number} irWatts - IR signature in watts
 * @returns {string} Human-readable mass class
 */
function classifyMass(irWatts) {
  if (irWatts == null || irWatts <= 0) return "--";
  for (const t of MASS_THRESHOLDS) {
    if (irWatts < t.max) return t.label;
  }
  return "--";
}

/**
 * Estimate drive state from IR signature.
 * @param {number} irWatts - IR signature in watts
 * @returns {string} Drive state label
 */
function estimateDriveState(irWatts) {
  if (irWatts == null || irWatts <= 0) return "--";
  if (irWatts >= DRIVE_THRESHOLDS.high) return "ACTIVE BURN";
  if (irWatts >= DRIVE_THRESHOLDS.medium) return "MANEUVERING";
  return "COASTING/COLD";
}

/**
 * Compute SNR in dB from IR signature, noise floor, and range.
 * SNR = ir_signature / (noise_floor * range^2)
 * @param {number} irWatts - IR signature (W)
 * @param {number} noiseFloor - Noise floor (W/m^2)
 * @param {number} range - Range in meters
 * @returns {number|null} SNR in dB, or null if inputs are invalid
 */
function computeSNR(irWatts, noiseFloor, range) {
  if (!irWatts || !noiseFloor || !range || range <= 0) return null;
  const snrLinear = irWatts / (noiseFloor * range * range);
  if (snrLinear <= 0) return null;
  return 10 * Math.log10(snrLinear);
}

/**
 * Get a quality color class based on a 0-1 value.
 * @param {number} value - Quality metric (0-1)
 * @returns {string} CSS class name
 */
function qualityClass(value) {
  if (value == null) return "val-dim";
  if (value >= 0.7) return "val-good";
  if (value >= 0.4) return "val-marginal";
  return "val-poor";
}

/**
 * Get SNR quality class based on dB value.
 * @param {number} snrDb - SNR in decibels
 * @returns {string} CSS class name
 */
function snrClass(snrDb) {
  if (snrDb == null) return "val-dim";
  if (snrDb >= 20) return "val-good";
  if (snrDb >= 6) return "val-marginal";
  return "val-poor";
}

/**
 * Format a number with engineering notation for large/small values.
 * @param {number} value
 * @returns {string}
 */
function formatEngineering(value) {
  if (value == null || value === 0) return "--";
  if (Math.abs(value) >= 1e9) return (value / 1e9).toFixed(1) + " GW";
  if (Math.abs(value) >= 1e6) return (value / 1e6).toFixed(1) + " MW";
  if (Math.abs(value) >= 1e3) return (value / 1e3).toFixed(1) + " kW";
  if (Math.abs(value) >= 1) return value.toFixed(1) + " W";
  return value.toExponential(1) + " W";
}

/**
 * Format distance with appropriate unit.
 * @param {number} meters
 * @returns {string}
 */
function formatRange(meters) {
  if (meters == null) return "--";
  if (meters >= 1e6) return (meters / 1e3).toFixed(0) + " km";
  if (meters >= 1e3) return (meters / 1e3).toFixed(1) + " km";
  return meters.toFixed(0) + " m";
}

/**
 * Format bearing degrees.
 * @param {object|number} bearing - Bearing value or {azimuth, elevation} object
 * @returns {string}
 */
function formatBearing(bearing) {
  if (bearing == null) return "--";
  if (typeof bearing === "object") {
    const az = bearing.azimuth != null ? bearing.azimuth.toFixed(1) : "--";
    const el = bearing.elevation != null ? bearing.elevation.toFixed(1) : "--";
    return `${az} / ${el}`;
  }
  return typeof bearing === "number" ? bearing.toFixed(1) + "\u00B0" : "--";
}

class SensorAnalysisManual extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._selectedContact = null;
    this._lastUpdate = 0;
    this._contactSelectedHandler = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this._render();

    // Subscribe to state updates (throttled in _onStateUpdate)
    this._unsub = stateManager.subscribe("*", () => this._onStateUpdate());

    // Listen for contact selection from tactical map / sensor contacts
    this._contactSelectedHandler = (e) => {
      this._selectedContact = e.detail?.contactId || null;
      this._updateDisplay();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);

    // Tier changes
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
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  /** Throttle state updates to 5 Hz */
  _onStateUpdate() {
    if (!this.offsetParent) return;
    const now = performance.now();
    if (now - this._lastUpdate < 200) return;
    this._lastUpdate = now;
    this._updateDisplay();
  }

  /** Find the selected contact from current sensor state */
  _getSelectedContact() {
    const state = stateManager.getState();
    const sensors = state?.sensors;
    if (!sensors?.contacts?.length) return null;
    if (!this._selectedContact) return null;

    return sensors.contacts.find(
      (c) => c.id === this._selectedContact
    ) || null;
  }

  /** Get all contacts for the selector dropdown */
  _getAllContacts() {
    const state = stateManager.getState();
    const sensors = state?.sensors;
    return sensors?.contacts || [];
  }

  /** Get sensor system noise floor estimate.
   *  Falls back to a reasonable default if not provided in telemetry. */
  _getNoiseFloor() {
    const state = stateManager.getState();
    // Check several possible locations for noise floor data
    const sensors = state?.sensors;
    if (sensors?.noise_floor != null) return sensors.noise_floor;
    // Passive sensor sensitivity is the noise floor
    if (sensors?.ir_sensitivity != null) return sensors.ir_sensitivity;
    // Fallback: typical passive IR sensor noise floor ~1e-8 W/m^2
    return 1e-8;
  }

  _updateDisplay() {
    const contact = this._getSelectedContact();
    const grid = this.shadowRoot.querySelector(".data-grid");
    const footer = this.shadowRoot.querySelector(".footer-grid");
    const emptyMsg = this.shadowRoot.querySelector(".empty-state");
    const contactSelector = this.shadowRoot.querySelector(".contact-select");

    if (!grid || !emptyMsg) return;

    // Update contact dropdown
    this._updateContactSelector(contactSelector);

    if (!contact) {
      grid.style.display = "none";
      if (footer) footer.style.display = "none";
      emptyMsg.style.display = "flex";
      return;
    }

    grid.style.display = "grid";
    if (footer) footer.style.display = "grid";
    emptyMsg.style.display = "none";

    const noiseFloor = this._getNoiseFloor();
    const irSig = contact.signature || null;
    const range = contact.distance || null;
    const snr = computeSNR(irSig, noiseFloor, range);
    const detQuality = contact.confidence || null;
    const detProb = detQuality != null ? (detQuality * 100) : null;

    // Compute time since last detection
    const state = stateManager.getState();
    const simTime = state?.sim_time || 0;
    const lastUpdate = contact.last_update || 0;
    const staleSec = simTime > 0 && lastUpdate > 0 ? (simTime - lastUpdate) : null;
    const isStale = staleSec != null && staleSec > 2.0;

    // Header line
    this._setText(".val-contact-id", contact.id || "--");
    this._setText(".val-classification",
      contact.classification || classifyMass(irSig) || "--");

    // Row 1: Bearing / Range
    this._setText(".val-bearing", formatBearing(contact.bearing));
    this._setText(".val-range", formatRange(range));

    // Row 2: IR Signature / Noise Floor
    this._setText(".val-ir-sig", formatEngineering(irSig));
    this._setText(".val-noise-floor", noiseFloor != null
      ? noiseFloor.toExponential(1) + " W/m\u00B2" : "--");

    // Row 3: SNR / Detection Quality
    const snrEl = this.shadowRoot.querySelector(".val-snr");
    if (snrEl) {
      snrEl.textContent = snr != null ? (snr >= 0 ? "+" : "") + snr.toFixed(1) + " dB" : "--";
      snrEl.className = "val val-snr " + snrClass(snr);
    }

    const detEl = this.shadowRoot.querySelector(".val-det-qual");
    if (detEl) {
      detEl.textContent = detQuality != null ? detQuality.toFixed(2) : "--";
      detEl.className = "val val-det-qual " + qualityClass(detQuality);
    }

    // Row 4: Detection Probability / Confidence
    const probEl = this.shadowRoot.querySelector(".val-det-prob");
    if (probEl) {
      probEl.textContent = detProb != null ? detProb.toFixed(0) + "%" : "--";
      probEl.className = "val val-det-prob " + qualityClass(detQuality);
    }

    const confEl = this.shadowRoot.querySelector(".val-confidence");
    if (confEl) {
      const conf = contact.confidence;
      confEl.textContent = conf != null ? conf.toFixed(2) : "--";
      confEl.className = "val val-confidence " + qualityClass(conf);
    }

    // Footer: Drive state, mass estimate, staleness
    const driveState = estimateDriveState(irSig);
    this._setText(".val-drive-state", driveState);
    const driveEl = this.shadowRoot.querySelector(".val-drive-state");
    if (driveEl) {
      driveEl.className = "val val-drive-state " +
        (driveState === "ACTIVE BURN" ? "val-poor" :
          driveState === "MANEUVERING" ? "val-marginal" : "val-good");
    }

    this._setText(".val-mass-est", classifyMass(irSig));
    this._setText(".val-last-seen",
      staleSec != null ? staleSec.toFixed(1) + "s ago" : "--");

    const staleEl = this.shadowRoot.querySelector(".val-stale");
    if (staleEl) {
      staleEl.textContent = isStale ? "YES" : "NO";
      staleEl.className = "val val-stale " + (isStale ? "val-poor" : "val-good");
    }

    // Detection method badge
    this._setText(".val-det-method",
      (contact.detection_method || "passive").toUpperCase());
  }

  /** Update contact selector dropdown options */
  _updateContactSelector(select) {
    if (!select) return;
    const contacts = this._getAllContacts();

    // Build option list
    const optionHtml = contacts.map((c) => {
      const label = c.name || c.classification || c.id;
      const dist = c.distance != null ? ` (${formatRange(c.distance)})` : "";
      const selected = c.id === this._selectedContact ? " selected" : "";
      return `<option value="${c.id}"${selected}>${c.id}: ${label}${dist}</option>`;
    }).join("");

    const newHtml = `<option value="">-- SELECT CONTACT --</option>` + optionHtml;

    // Only update DOM if options changed (avoid flicker)
    if (select._lastHtml !== newHtml) {
      select.innerHTML = newHtml;
      select._lastHtml = newHtml;
    }
  }

  /** Helper to set text content by selector */
  _setText(selector, text) {
    const el = this.shadowRoot.querySelector(selector);
    if (el) el.textContent = text ?? "--";
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: "JetBrains Mono", "Courier New", monospace;
          font-size: 0.8rem;
          color: #c8c8c8;
          line-height: 1.4;
        }

        .container {
          padding: 8px;
        }

        /* Contact selector */
        .contact-selector-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        .contact-select {
          flex: 1;
          background: #0a0a14;
          color: #ff8800;
          border: 1px solid #ff880044;
          border-radius: 2px;
          font-family: inherit;
          font-size: 0.75rem;
          padding: 4px 6px;
          outline: none;
        }

        .contact-select:focus {
          border-color: #ff8800;
        }

        /* Header row */
        .header-row {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          padding: 4px 0;
          border-bottom: 1px solid #ff880044;
          margin-bottom: 6px;
        }

        .header-label {
          color: #ff8800;
          font-weight: 600;
          font-size: 0.85rem;
        }

        .header-value {
          color: #ff8800;
          font-size: 0.75rem;
        }

        .det-method-badge {
          display: inline-block;
          padding: 1px 6px;
          border: 1px solid #ff880066;
          border-radius: 2px;
          font-size: 0.65rem;
          color: #ff8800;
          margin-left: 8px;
        }

        /* Two-column data grid */
        .data-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 2px 16px;
          background: #06060c;
          padding: 6px 8px;
          border: 1px solid #ff880022;
          border-radius: 2px;
        }

        .data-cell {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          padding: 2px 0;
        }

        .label {
          color: #888;
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          white-space: nowrap;
        }

        .val {
          font-size: 0.8rem;
          text-align: right;
          white-space: nowrap;
        }

        /* Value color classes */
        .val-good { color: #44cc44; }
        .val-marginal { color: #ccaa22; }
        .val-poor { color: #cc4444; }
        .val-dim { color: #666; }

        /* Section divider */
        .divider {
          grid-column: span 2;
          border: none;
          border-top: 1px solid #ff880033;
          margin: 4px 0;
        }

        /* Footer section */
        .footer-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 2px 16px;
          margin-top: 6px;
          padding: 6px 8px;
          background: #06060c;
          border: 1px solid #ff880022;
          border-radius: 2px;
        }

        /* Empty state */
        .empty-state {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100px;
          color: #555;
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
      </style>

      <div class="container">
        <div class="contact-selector-row">
          <select class="contact-select"></select>
        </div>

        <div class="header-row">
          <span>
            <span class="header-label">CONTACT: </span>
            <span class="header-value val-contact-id">--</span>
            <span class="det-method-badge val-det-method">--</span>
          </span>
          <span>
            <span class="header-label">CLASS: </span>
            <span class="header-value val-classification">--</span>
          </span>
        </div>

        <div class="data-grid" style="display: none;">
          <div class="data-cell">
            <span class="label">BEARING</span>
            <span class="val val-bearing">--</span>
          </div>
          <div class="data-cell">
            <span class="label">RANGE</span>
            <span class="val val-range">--</span>
          </div>

          <div class="data-cell">
            <span class="label">IR SIG</span>
            <span class="val val-ir-sig">--</span>
          </div>
          <div class="data-cell">
            <span class="label">NOISE FLR</span>
            <span class="val val-noise-floor">--</span>
          </div>

          <div class="data-cell">
            <span class="label">SNR</span>
            <span class="val val-snr val-dim">--</span>
          </div>
          <div class="data-cell">
            <span class="label">DET QUAL</span>
            <span class="val val-det-qual val-dim">--</span>
          </div>

          <hr class="divider">

          <div class="data-cell">
            <span class="label">DET PROB</span>
            <span class="val val-det-prob val-dim">--</span>
          </div>
          <div class="data-cell">
            <span class="label">CONFIDENCE</span>
            <span class="val val-confidence val-dim">--</span>
          </div>
        </div>

        <div class="footer-grid" style="display: none;">
          <div class="data-cell">
            <span class="label">DRIVE STATE</span>
            <span class="val val-drive-state val-dim">--</span>
          </div>
          <div class="data-cell">
            <span class="label">EST MASS</span>
            <span class="val val-mass-est">--</span>
          </div>
          <div class="data-cell">
            <span class="label">LAST SEEN</span>
            <span class="val val-last-seen">--</span>
          </div>
          <div class="data-cell">
            <span class="label">STALE</span>
            <span class="val val-stale val-dim">--</span>
          </div>
        </div>

        <div class="empty-state">SELECT A CONTACT FOR ANALYSIS</div>
      </div>
    `;

    // Wire up contact selector change
    const select = this.shadowRoot.querySelector(".contact-select");
    select.addEventListener("change", (e) => {
      this._selectedContact = e.target.value || null;
      // Dispatch contact-selected so other panels sync
      if (this._selectedContact) {
        document.dispatchEvent(new CustomEvent("contact-selected", {
          bubbles: true,
          composed: true,
          detail: { contactId: this._selectedContact },
        }));
      }
      this._updateDisplay();
    });
  }

}

customElements.define("sensor-analysis-manual", SensorAnalysisManual);
