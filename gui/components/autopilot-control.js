/**
 * Autopilot Control
 * Mode selector, target dropdown, engage/disengage
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const AUTOPILOT_MODES = [
  { id: "manual", label: "MANUAL", description: "Direct control" },
  { id: "intercept", label: "INTERCEPT", description: "Approach target" },
  { id: "match", label: "MATCH", description: "Match velocity" },
  { id: "hold", label: "HOLD", description: "Hold position" },
  { id: "hold_velocity", label: "HOLD VEL", description: "Maintain velocity" },
];

class AutopilotControl extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._selectedMode = "manual";
    this._selectedTarget = null;
    this._contactSelectedHandler = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();

    // Listen for contact selection
    this._contactSelectedHandler = (e) => {
      this._selectedTarget = e.detail.contactId;
      this._updateTargetDropdown();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
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
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .mode-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 6px;
          margin-bottom: 16px;
        }

        .mode-btn {
          padding: 10px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-secondary, #888899);
          cursor: pointer;
          font-size: 0.75rem;
          font-weight: 600;
          min-height: 44px;
          transition: all 0.1s ease;
        }

        .mode-btn:hover {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        .mode-btn.selected {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .mode-btn.active {
          box-shadow: 0 0 12px rgba(0, 170, 255, 0.3);
        }

        .target-section {
          margin-bottom: 16px;
        }

        .target-select {
          width: 100%;
          padding: 10px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          cursor: pointer;
          min-height: 44px;
        }

        .target-select:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .action-buttons {
          display: flex;
          gap: 8px;
        }

        .action-btn {
          flex: 1;
          padding: 12px 16px;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 44px;
        }

        .engage-btn {
          background: var(--status-nominal, #00ff88);
          border: none;
          color: var(--bg-primary, #0a0a0f);
        }

        .engage-btn:hover {
          filter: brightness(1.1);
        }

        .engage-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .disengage-btn {
          background: transparent;
          border: 1px solid var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .disengage-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .status-box {
          margin-top: 16px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .status-row {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
        }

        .status-label {
          color: var(--text-dim, #555566);
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-primary, #e0e0e0);
        }

        .status-value.active {
          color: var(--status-info, #00aaff);
        }
      </style>

      <div class="section-title">Mode</div>
      <div class="mode-grid" id="mode-grid"></div>

      <div class="target-section">
        <div class="section-title">Target</div>
        <select class="target-select" id="target-select">
          <option value="">-- Select Target --</option>
        </select>
      </div>

      <div class="action-buttons">
        <button class="action-btn engage-btn" id="engage-btn">ENGAGE</button>
        <button class="action-btn disengage-btn" id="disengage-btn">DISENGAGE</button>
      </div>

      <div class="status-box">
        <div class="status-row">
          <span class="status-label">Status:</span>
          <span class="status-value" id="status-text">MANUAL CONTROL</span>
        </div>
      </div>
    `;
  }

  _setupInteraction() {
    // Render mode buttons
    this._renderModeButtons();

    // Target select
    const targetSelect = this.shadowRoot.getElementById("target-select");
    targetSelect.addEventListener("change", () => {
      this._selectedTarget = targetSelect.value || null;
    });

    // Engage button
    this.shadowRoot.getElementById("engage-btn").addEventListener("click", () => {
      this._engage();
    });

    // Disengage button
    this.shadowRoot.getElementById("disengage-btn").addEventListener("click", () => {
      this._disengage();
    });
  }

  _renderModeButtons() {
    const grid = this.shadowRoot.getElementById("mode-grid");
    grid.innerHTML = AUTOPILOT_MODES.map(mode => `
      <button 
        class="mode-btn ${mode.id === this._selectedMode ? 'selected' : ''}" 
        data-mode="${mode.id}"
        title="${mode.description}"
      >
        ${mode.label}
      </button>
    `).join("");

    grid.querySelectorAll(".mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._selectedMode = btn.dataset.mode;
        this._renderModeButtons();
        this._updateEngageButton();
      });
    });
  }

  _updateTargetDropdown() {
    const contacts = stateManager.getContacts();
    const select = this.shadowRoot.getElementById("target-select");
    const currentValue = this._selectedTarget;

    select.innerHTML = '<option value="">-- Select Target --</option>';

    contacts.forEach(contact => {
      const id = contact.contact_id || contact.id;
      const option = document.createElement("option");
      option.value = id;
      option.textContent = `${id} (${contact.classification || "UNKNOWN"})`;
      if (id === currentValue) {
        option.selected = true;
      }
      select.appendChild(option);
    });

    if (currentValue && !contacts.find(c => (c.contact_id || c.id) === currentValue)) {
      // Keep the previously selected value even if not in contacts
      const option = document.createElement("option");
      option.value = currentValue;
      option.textContent = currentValue;
      option.selected = true;
      select.appendChild(option);
    }
  }

  _updateEngageButton() {
    const engageBtn = this.shadowRoot.getElementById("engage-btn");
    const needsTarget = ["intercept", "match"].includes(this._selectedMode);
    engageBtn.disabled = needsTarget && !this._selectedTarget;
  }

  _updateDisplay() {
    this._updateTargetDropdown();

    const nav = stateManager.getNavigation();
    const autopilot = nav.autopilot;
    const statusText = this.shadowRoot.getElementById("status-text");

    if (autopilot && autopilot.mode && autopilot.mode !== "off" && autopilot.mode !== "manual") {
      const modeLabel = AUTOPILOT_MODES.find(m => m.id === autopilot.mode)?.label || autopilot.mode.toUpperCase();
      const targetInfo = autopilot.target ? ` → ${autopilot.target}` : "";
      const phaseInfo = autopilot.phase ? ` (${autopilot.phase})` : "";
      statusText.textContent = `${modeLabel}${targetInfo}${phaseInfo}`;
      statusText.classList.add("active");

      // Highlight active mode
      this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.mode === autopilot.mode);
      });
    } else {
      statusText.textContent = "MANUAL CONTROL";
      statusText.classList.remove("active");

      this.shadowRoot.querySelectorAll(".mode-btn").forEach(btn => {
        btn.classList.remove("active");
      });
    }

    this._updateEngageButton();
  }

  async _engage() {
    const mode = this._selectedMode;
    const target = this._selectedTarget;

    if (mode === "manual") {
      await this._disengage();
      return;
    }

    try {
      // Server expects "program" not "mode" for autopilot commands
      const args = { program: mode };
      if (target) {
        args.target = target;
      }
      console.log("Engaging autopilot:", args);
      const response = await wsClient.sendShipCommand("autopilot", args);
      console.log("Autopilot response:", response);
      
      if (response && response.error) {
        this._showMessage(`Autopilot error: ${response.error}`, "error");
      } else {
        this._showMessage(`Autopilot ${mode} engaged`, "success");
      }
    } catch (error) {
      console.error("Autopilot engage failed:", error);
      this._showMessage(`Autopilot failed: ${error.message}`, "error");
    }
  }

  async _disengage() {
    try {
      // Use "off" program to disengage
      console.log("Disengaging autopilot");
      const response = await wsClient.sendShipCommand("autopilot", { program: "off" });
      console.log("Disengage response:", response);
      this._showMessage("Autopilot disengaged", "info");
    } catch (error) {
      console.error("Autopilot disengage failed:", error);
      this._showMessage(`Disengage failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("autopilot-control", AutopilotControl);
export { AutopilotControl };
