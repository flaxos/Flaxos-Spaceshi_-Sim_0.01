/**
 * Sensor Contacts Panel
 * Displays contacts list, ping status, active scanning
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class SensorContacts extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._selectedContact = null;
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
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          height: 100%;
          display: flex;
          flex-direction: column;
        }

        .sensor-status {
          padding: 12px 16px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .status-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .status-row:last-child {
          margin-bottom: 0;
        }

        .status-label {
          color: var(--text-secondary, #888899);
          font-size: 0.75rem;
        }

        .status-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .status-indicator {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }

        .status-indicator.active {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 6px var(--status-nominal, #00ff88);
        }

        .status-indicator.ready {
          background: var(--status-info, #00aaff);
        }

        .status-indicator.cooldown {
          background: var(--status-warning, #ffaa00);
        }

        .cooldown-bar {
          flex: 1;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
          margin-left: 8px;
        }

        .cooldown-fill {
          height: 100%;
          background: var(--status-warning, #ffaa00);
          transition: width 0.2s ease;
        }

        .ping-btn {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          padding: 4px 12px;
          cursor: pointer;
          font-size: 0.7rem;
          transition: all 0.1s ease;
          min-height: auto;
        }

        .ping-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .ping-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .contacts-header {
          padding: 8px 16px;
          display: grid;
          grid-template-columns: 50px 70px 50px 60px 60px;
          gap: 6px;
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .contacts-list {
          flex: 1;
          overflow-y: auto;
          padding: 8px 0;
        }

        .contact-row {
          display: grid;
          grid-template-columns: 50px 70px 50px 60px 60px;
          gap: 6px;
          padding: 8px 16px;
          cursor: pointer;
          transition: background 0.1s ease;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
        }

        .contact-expanded {
          padding: 8px 16px;
          background: rgba(0, 170, 255, 0.05);
          border-left: 2px solid var(--status-info, #00aaff);
          font-size: 0.7rem;
          display: none;
        }

        .contact-expanded.visible {
          display: block;
        }

        .position-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-bottom: 8px;
        }

        .pos-item {
          text-align: center;
        }

        .pos-label {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
        }

        .pos-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-secondary, #888899);
        }

        .contact-actions {
          display: flex;
          gap: 8px;
          margin-top: 8px;
        }

        .contact-action-btn {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.7rem;
          cursor: pointer;
          min-height: auto;
        }

        .contact-action-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .contact-action-btn.primary {
          background: var(--status-info, #00aaff);
          border-color: var(--status-info, #00aaff);
          color: var(--bg-primary, #0a0a0f);
        }

        .contact-row:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .contact-row.selected {
          background: rgba(0, 170, 255, 0.1);
          border-left: 2px solid var(--status-info, #00aaff);
        }

        .contact-id {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .contact-class {
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          font-size: 0.7rem;
        }

        .contact-bearing {
          color: var(--text-primary, #e0e0e0);
        }

        .contact-range {
          color: var(--text-secondary, #888899);
        }

        .contact-closure {
          font-size: 0.7rem;
        }

        .contact-closure.closing {
          color: var(--status-critical, #ff4444);
        }

        .contact-closure.opening {
          color: var(--status-nominal, #00ff88);
        }

        .contact-footer {
          padding: 8px 16px;
          border-top: 1px solid var(--border-default, #2a2a3a);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        .confidence-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }

        .confidence-bar {
          flex: 1;
          height: 6px;
          background: var(--bg-input, #1a1a24);
          border-radius: 3px;
          overflow: hidden;
        }

        .confidence-fill {
          height: 100%;
          background: var(--status-nominal, #00ff88);
          transition: width 0.2s ease;
        }

        .confidence-fill.medium {
          background: var(--status-warning, #ffaa00);
        }

        .confidence-fill.low {
          background: var(--status-critical, #ff4444);
        }

        .empty-state {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: var(--text-dim, #555566);
          padding: 24px;
        }

        .empty-icon {
          font-size: 2rem;
          margin-bottom: 8px;
          opacity: 0.5;
        }

        .select-indicator {
          width: 8px;
          color: var(--status-info, #00aaff);
        }
      </style>

      <div class="sensor-status">
        <div class="status-row">
          <span class="status-label">PASSIVE</span>
          <span class="status-value">
            <span class="status-indicator active"></span>
            SCANNING
          </span>
        </div>
        <div class="status-row">
          <span class="status-label">ACTIVE PING</span>
          <span class="status-value" id="ping-status">
            <span class="status-indicator ready"></span>
            READY
          </span>
          <button class="ping-btn" id="ping-btn">📡 PING</button>
        </div>
        <div class="status-row" id="cooldown-row" style="display: none;">
          <span class="status-label">COOLDOWN</span>
          <div class="cooldown-bar">
            <div class="cooldown-fill" id="cooldown-fill"></div>
          </div>
          <span id="cooldown-text">0s</span>
        </div>
      </div>

      <div class="contacts-header">
        <span>ID</span>
        <span>CLASS</span>
        <span>BRG</span>
        <span>RANGE</span>
        <span>CLOSURE</span>
      </div>

      <div class="contacts-list" id="contacts-list">
        <div class="empty-state">
          <div class="empty-icon">○</div>
          <div>No contacts in range</div>
        </div>
      </div>

      <div class="contact-footer" id="footer">
        <div class="confidence-row">
          <span>Confidence:</span>
          <div class="confidence-bar">
            <div class="confidence-fill" id="confidence-fill" style="width: 0%"></div>
          </div>
          <span id="confidence-text">--%</span>
        </div>
        <div>Last Update: <span id="last-update">--</span></div>
      </div>
    `;

    this._setupEvents();
  }

  _setupEvents() {
    const pingBtn = this.shadowRoot.getElementById("ping-btn");
    pingBtn.addEventListener("click", () => this._doPing());

    const contactsList = this.shadowRoot.getElementById("contacts-list");
    contactsList.addEventListener("click", (e) => {
      // Handle action buttons
      const actionBtn = e.target.closest(".contact-action-btn");
      if (actionBtn) {
        const action = actionBtn.dataset.action;
        const contactId = actionBtn.dataset.contact;
        this._handleContactAction(action, contactId);
        return;
      }

      // Handle row selection
      const row = e.target.closest(".contact-row");
      if (row) {
        this._selectContact(row.dataset.contactId);
      }
    });
  }

  async _handleContactAction(action, contactId) {
    const contacts = stateManager.getContacts();
    const contact = contacts.find(c => (c.contact_id || c.id) === contactId);
    
    if (!contact) {
      console.error("Contact not found:", contactId);
      return;
    }

    if (action === "point") {
      // Point at target - calculate bearing and set orientation
      let targetYaw = contact.bearing ?? contact.bearing_to;
      
      if (targetYaw === undefined && contact.position) {
        // Calculate bearing from position
        const ship = stateManager.getShipState();
        const shipPos = ship?.position || { x: 0, y: 0, z: 0 };
        const targetPos = contact.position;
        
        const dx = (targetPos.x ?? targetPos[0] ?? 0) - (shipPos.x ?? shipPos[0] ?? 0);
        const dy = (targetPos.y ?? targetPos[1] ?? 0) - (shipPos.y ?? shipPos[1] ?? 0);
        
        // Calculate yaw angle
        targetYaw = Math.atan2(dy, dx) * (180 / Math.PI);
        targetYaw = (90 - targetYaw + 360) % 360;
      }

      if (targetYaw !== undefined) {
        try {
          console.log("Pointing at contact:", contactId, "bearing:", targetYaw);
          await wsClient.sendShipCommand("set_orientation", {
            pitch: 0,
            yaw: targetYaw,
            roll: 0
          });
          this._showMessage(`Pointing at ${contactId}`, "info");
        } catch (error) {
          console.error("Point at target failed:", error);
          this._showMessage(`Point failed: ${error.message}`, "error");
        }
      }
    } else if (action === "lock") {
      // Lock target
      try {
        console.log("Locking target:", contactId);
        await wsClient.sendShipCommand("lock_target", {
          target_id: contactId
        });
        this._showMessage(`Target locked: ${contactId}`, "info");
      } catch (error) {
        console.error("Lock target failed:", error);
        this._showMessage(`Lock failed: ${error.message}`, "error");
      }
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }

  async _doPing() {
    const pingBtn = this.shadowRoot.getElementById("ping-btn");
    pingBtn.disabled = true;

    try {
      await wsClient.sendShipCommand("ping_sensors", {});
    } catch (error) {
      console.error("Ping failed:", error);
    }

    // Button re-enabled on next state update
  }

  _selectContact(contactId) {
    this._selectedContact = contactId;
    this._updateContactSelection();

    // Dispatch event for other components
    this.dispatchEvent(new CustomEvent("contact-selected", {
      detail: { contactId },
      bubbles: true
    }));
  }

  _updateContactSelection() {
    const rows = this.shadowRoot.querySelectorAll(".contact-row");
    rows.forEach(row => {
      row.classList.toggle("selected", row.dataset.contactId === this._selectedContact);
    });
  }

  _updateDisplay() {
    const contacts = stateManager.getContacts();
    const sensors = stateManager.getSensors();

    this._updatePingStatus(sensors);
    this._updateContactsList(contacts);
    this._updateFooter(sensors);
  }

  _updatePingStatus(sensors) {
    const pingStatus = this.shadowRoot.getElementById("ping-status");
    const pingBtn = this.shadowRoot.getElementById("ping-btn");
    const cooldownRow = this.shadowRoot.getElementById("cooldown-row");
    const cooldownFill = this.shadowRoot.getElementById("cooldown-fill");
    const cooldownText = this.shadowRoot.getElementById("cooldown-text");

    // Handle different sensor state structures
    const active = sensors.active || {};
    const canPing = sensors.can_ping ?? active.can_ping ?? true;
    const cooldown = sensors.ping_cooldown_remaining ?? active.cooldown_remaining ?? sensors.cooldown ?? 0;
    const maxCooldown = sensors.ping_cooldown ?? active.cooldown ?? 30;

    if (canPing && cooldown <= 0) {
      pingStatus.innerHTML = '<span class="status-indicator ready"></span> READY';
      pingBtn.disabled = false;
      cooldownRow.style.display = "none";
    } else {
      pingStatus.innerHTML = '<span class="status-indicator cooldown"></span> COOLDOWN';
      pingBtn.disabled = true;
      cooldownRow.style.display = "flex";

      const percent = maxCooldown > 0 ? (cooldown / maxCooldown) * 100 : 0;
      cooldownFill.style.width = `${percent}%`;
      cooldownText.textContent = `${cooldown.toFixed(0)}s`;
    }
  }

  _updateContactsList(contacts) {
    const list = this.shadowRoot.getElementById("contacts-list");

    if (!contacts || contacts.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">○</div>
          <div>No contacts in range</div>
        </div>
      `;
      return;
    }

    // Sort by range (nearest first)
    const sorted = [...contacts].sort((a, b) => {
      const rangeA = a.range || a.distance || Infinity;
      const rangeB = b.range || b.distance || Infinity;
      return rangeA - rangeB;
    });

    list.innerHTML = sorted.map(contact => this._renderContactRow(contact)).join("");
    this._updateContactSelection();
  }

  _renderContactRow(contact) {
    const id = contact.contact_id || contact.id || "???";
    const classification = contact.classification || contact.class || "UNKNOWN";
    const bearing = contact.bearing ?? "---";
    const range = contact.range ?? contact.distance ?? 0;
    const rangeRate = contact.range_rate ?? contact.closure ?? 0;

    const isSelected = id === this._selectedContact;
    const closureClass = rangeRate < 0 ? "closing" : rangeRate > 0 ? "opening" : "";
    const closureSign = rangeRate < 0 ? "-" : rangeRate > 0 ? "+" : "";

    // Get position info
    const pos = contact.position || contact.pos || {};
    const posX = pos.x ?? pos[0] ?? 0;
    const posY = pos.y ?? pos[1] ?? 0;
    const posZ = pos.z ?? pos[2] ?? 0;

    // Get relative position from player ship
    const ship = stateManager.getShipState();
    const shipPos = ship?.position || ship?.pos || {};
    const shipX = shipPos.x ?? shipPos[0] ?? 0;
    const shipY = shipPos.y ?? shipPos[1] ?? 0;
    const shipZ = shipPos.z ?? shipPos[2] ?? 0;

    const relX = posX - shipX;
    const relY = posY - shipY;
    const relZ = posZ - shipZ;

    return `
      <div class="contact-row ${isSelected ? 'selected' : ''}" data-contact-id="${id}">
        <span class="contact-id">${isSelected ? '►' : ' '}${id.substring(0, 5)}</span>
        <span class="contact-class">${classification.substring(0, 8)}</span>
        <span class="contact-bearing">${this._formatBearing(bearing)}°</span>
        <span class="contact-range">${this._formatRange(range)}</span>
        <span class="contact-closure ${closureClass}">${closureSign}${Math.abs(rangeRate).toFixed(0)}</span>
      </div>
      <div class="contact-expanded ${isSelected ? 'visible' : ''}" data-contact-id="${id}">
        <div class="position-grid">
          <div class="pos-item">
            <div class="pos-label">Rel X</div>
            <div class="pos-value">${this._formatDistance(relX)}</div>
          </div>
          <div class="pos-item">
            <div class="pos-label">Rel Y</div>
            <div class="pos-value">${this._formatDistance(relY)}</div>
          </div>
          <div class="pos-item">
            <div class="pos-label">Rel Z</div>
            <div class="pos-value">${this._formatDistance(relZ)}</div>
          </div>
        </div>
        <div class="position-grid">
          <div class="pos-item">
            <div class="pos-label">Abs X</div>
            <div class="pos-value">${this._formatDistance(posX)}</div>
          </div>
          <div class="pos-item">
            <div class="pos-label">Abs Y</div>
            <div class="pos-value">${this._formatDistance(posY)}</div>
          </div>
          <div class="pos-item">
            <div class="pos-label">Abs Z</div>
            <div class="pos-value">${this._formatDistance(posZ)}</div>
          </div>
        </div>
        <div class="contact-actions">
          <button class="contact-action-btn primary" data-action="point" data-contact="${id}">Point At</button>
          <button class="contact-action-btn" data-action="lock" data-contact="${id}">Lock Target</button>
        </div>
      </div>
    `;
  }

  _formatDistance(meters) {
    if (Math.abs(meters) >= 1000) {
      return `${(meters / 1000).toFixed(1)}km`;
    }
    return `${meters.toFixed(0)}m`;
  }

  _updateFooter(sensors) {
    const confidenceFill = this.shadowRoot.getElementById("confidence-fill");
    const confidenceText = this.shadowRoot.getElementById("confidence-text");
    const lastUpdate = this.shadowRoot.getElementById("last-update");

    const confidence = sensors.confidence ?? sensors.accuracy ?? 78;
    confidenceFill.style.width = `${confidence}%`;
    confidenceFill.className = `confidence-fill ${confidence > 70 ? '' : confidence > 40 ? 'medium' : 'low'}`;
    confidenceText.textContent = `${confidence.toFixed(0)}%`;

    const age = stateManager.getStateAge();
    if (age < 1000) {
      lastUpdate.textContent = "Just now";
    } else {
      lastUpdate.textContent = `${(age / 1000).toFixed(1)}s ago`;
    }
  }

  _formatBearing(bearing) {
    if (typeof bearing !== "number") return "---";
    return bearing.toFixed(0).padStart(3, "0");
  }

  _formatRange(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(1)} km`;
    }
    return `${meters.toFixed(0)} m`;
  }

  /**
   * Get currently selected contact ID
   */
  getSelectedContact() {
    return this._selectedContact;
  }
}

customElements.define("sensor-contacts", SensorContacts);
export { SensorContacts };
