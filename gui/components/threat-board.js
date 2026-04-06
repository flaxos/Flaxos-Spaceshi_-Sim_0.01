/**
 * Threat Board
 * Ranked threat list showing all contacts sorted by danger level
 * with engagement envelope indicators.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// Weapon engagement envelopes (meters)
const PDC_RANGE = 5000;        // 5 km
const RAILGUN_RANGE = 500000;  // 500 km

// Faction threat weights (higher = more dangerous)
const FACTION_WEIGHT = {
  hostile: 1.0,
  unknown: 0.6,
  neutral: 0.2,
  friendly: 0.0,
};

class ThreatBoard extends HTMLElement {
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

  /**
   * Calculate a 0-100 threat score for a contact.
   *
   * Factors:
   *  - Range: closer contacts score higher (inverse, capped at railgun range)
   *  - Closing speed: negative range_rate (closing) adds threat
   *  - Faction: hostile > unknown > neutral > friendly
   *  - Weapon envelope: being inside PDC range is an extreme threat multiplier
   */
  _calculateThreatScore(contact) {
    const range = contact.range ?? contact.distance ?? Infinity;
    const rangeRate = contact.range_rate ?? contact.closure ?? 0;
    const faction = (contact.faction || contact.iff || "unknown").toLowerCase();

    // Range component (0-40 points): inverse proportion to railgun range
    // At 0m => 40, at RAILGUN_RANGE => 0, beyond => 0
    const rangeFraction = Math.max(0, 1 - range / RAILGUN_RANGE);
    let rangeScore = rangeFraction * 40;

    // Closing speed component (0-25 points): only when closing (negative rate)
    // Normalize: -1000 m/s closing => 25 points
    let closureScore = 0;
    if (rangeRate < 0) {
      closureScore = Math.min(25, (Math.abs(rangeRate) / 1000) * 25);
    }

    // Faction component (0-25 points)
    const factionScore = (FACTION_WEIGHT[faction] ?? 0.6) * 25;

    // Envelope bonus (0-10 points): extra threat for being inside weapon range
    let envelopeScore = 0;
    if (range <= PDC_RANGE) {
      envelopeScore = 10;
    } else if (range <= RAILGUN_RANGE) {
      envelopeScore = 5;
    }

    return Math.min(100, rangeScore + closureScore + factionScore + envelopeScore);
  }

  /**
   * Determine the engagement envelope status string and CSS class.
   */
  _getEnvelopeStatus(range) {
    if (range <= PDC_RANGE) {
      return { text: "IN PDC RANGE", cls: "envelope-pdc" };
    }
    if (range <= RAILGUN_RANGE) {
      return { text: "IN RAILGUN RANGE", cls: "envelope-railgun" };
    }
    return { text: "OUT OF RANGE", cls: "envelope-none" };
  }

  /**
   * Map threat score to a severity tier for color coding.
   */
  _getThreatTier(score) {
    if (score >= 60) return "critical";   // red
    if (score >= 30) return "elevated";   // amber
    return "low";                          // green
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

        .board-header {
          padding: 10px 16px;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .board-title {
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: var(--text-secondary, #888899);
        }

        .contact-count {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
        }

        .contacts-header {
          padding: 6px 16px;
          padding-left: 22px; /* account for threat bar width + gap */
          display: grid;
          grid-template-columns: 60px 70px 70px 80px 110px 20px;
          gap: 6px;
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
        }

        .threat-list {
          flex: 1;
          overflow-y: auto;
          padding: 4px 0;
        }

        /* --- Contact row --- */
        .threat-row {
          display: flex;
          align-items: stretch;
          cursor: pointer;
          transition: background 0.1s ease;
          border-left: 3px solid transparent;
        }

        .threat-row:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .threat-row.locked {
          border-left-color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.08);
        }

        /* Colored threat bar on the left edge */
        .threat-bar {
          width: 3px;
          flex-shrink: 0;
        }

        .threat-bar.critical {
          background: var(--status-critical, #ff4444);
          box-shadow: 0 0 4px var(--status-critical, #ff4444);
        }

        .threat-bar.elevated {
          background: var(--status-warning, #ffaa00);
        }

        .threat-bar.low {
          background: var(--status-nominal, #00ff88);
        }

        .row-content {
          display: grid;
          grid-template-columns: 60px 70px 70px 80px 110px 20px;
          gap: 6px;
          padding: 7px 16px 7px 4px;
          flex: 1;
          align-items: center;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.72rem;
        }

        .contact-id {
          font-weight: 600;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .contact-id.hostile {
          color: var(--status-critical, #ff4444);
        }

        .contact-id.unknown {
          color: var(--status-warning, #ffaa00);
        }

        .contact-id.neutral {
          color: var(--text-secondary, #888899);
        }

        .contact-id.friendly {
          color: var(--status-nominal, #00ff88);
        }

        .contact-class {
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          font-size: 0.68rem;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .contact-range {
          color: var(--text-secondary, #888899);
        }

        .contact-closure {
          font-size: 0.68rem;
        }

        .contact-closure.closing {
          color: var(--status-critical, #ff4444);
        }

        .contact-closure.opening {
          color: var(--status-nominal, #00ff88);
        }

        .contact-closure.stable {
          color: var(--text-dim, #555566);
        }

        .envelope-tag {
          font-size: 0.58rem;
          font-weight: 600;
          letter-spacing: 0.3px;
          white-space: nowrap;
        }

        .envelope-tag.envelope-pdc {
          color: var(--status-critical, #ff4444);
        }

        .envelope-tag.envelope-railgun {
          color: var(--status-warning, #ffaa00);
        }

        .envelope-tag.envelope-none {
          color: var(--text-dim, #555566);
        }

        .lock-icon {
          text-align: center;
          font-size: 0.7rem;
          color: var(--status-info, #00aaff);
        }

        /* --- Quick-lock action overlay --- */
        .quick-lock {
          display: none;
          padding: 6px 16px 6px 22px;
          background: rgba(255, 68, 68, 0.06);
          border-bottom: 1px solid rgba(255, 68, 68, 0.15);
        }

        .quick-lock.visible {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .quick-lock-btn {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--status-critical, #ff4444);
          border-radius: 4px;
          color: var(--status-critical, #ff4444);
          padding: 4px 10px;
          cursor: pointer;
          font-size: 0.68rem;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-weight: 600;
          min-height: auto;
          transition: all 0.1s ease;
        }

        .quick-lock-btn:hover {
          background: rgba(255, 68, 68, 0.15);
        }

        .quick-lock-label {
          font-size: 0.68rem;
          color: var(--text-dim, #555566);
        }

        /* --- Empty state --- */
        .empty-state {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: var(--text-dim, #555566);
          padding: 32px 24px;
        }

        .empty-icon {
          font-size: 2rem;
          margin-bottom: 8px;
          opacity: 0.4;
        }

        .empty-text {
          font-size: 0.85rem;
        }
      </style>

      <div class="board-header">
        <span class="board-title">THREAT BOARD</span>
        <span class="contact-count" id="contact-count">0 contacts</span>
      </div>

      <div class="contacts-header">
        <span>ID</span>
        <span>CLASS</span>
        <span>RANGE</span>
        <span>CLOSURE</span>
        <span>ENVELOPE</span>
        <span></span>
      </div>

      <div class="threat-list" id="threat-list">
        <div class="empty-state">
          <div class="empty-icon">-</div>
          <div class="empty-text">No contacts detected</div>
        </div>
      </div>
    `;

    this._setupEvents();
  }

  _setupEvents() {
    const list = this.shadowRoot.getElementById("threat-list");

    list.addEventListener("click", (e) => {
      // Handle quick-lock button
      const lockBtn = e.target.closest(".quick-lock-btn");
      if (lockBtn) {
        const contactId = lockBtn.dataset.contact;
        this._lockTarget(contactId);
        return;
      }

      // Handle row click
      const row = e.target.closest(".threat-row");
      if (row) {
        this._onRowClicked(row.dataset.contactId);
      }
    });
  }

  _onRowClicked(contactId) {
    this._selectedContact = contactId;

    // Dispatch contact-selected event (same as sensor-contacts)
    this.dispatchEvent(new CustomEvent("contact-selected", {
      detail: { contactId },
      bubbles: true,
    }));

    // Re-render to show quick-lock if applicable
    this._updateDisplay();
  }

  async _lockTarget(contactId) {
    try {
      const result = await wsClient.sendShipCommand("lock_target", {
        contact_id: contactId,
      });
      if (result && result.ok === false) {
        console.error("Lock target failed:", result.message || result.error);
        this._showMessage(`Lock failed: ${result.message || result.error}`, "error");
      } else {
        this._showMessage(`Target locked: ${contactId}`, "info");
      }
    } catch (error) {
      console.error("Lock target failed:", error);
      this._showMessage(`Lock failed: ${error.message}`, "error");
    }
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }

  _updateDisplay() {
    const contacts = stateManager.getContacts();
    const targeting = stateManager.getTargeting();

    // Determine currently locked target
    const lockedId = targeting?.target_id || targeting?.id || null;

    const countEl = this.shadowRoot.getElementById("contact-count");
    const list = this.shadowRoot.getElementById("threat-list");

    if (!contacts || contacts.length === 0) {
      countEl.textContent = "0 contacts";
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">-</div>
          <div class="empty-text">No contacts detected</div>
        </div>
      `;
      return;
    }

    countEl.textContent = `${contacts.length} contact${contacts.length !== 1 ? "s" : ""}`;

    // Score and sort contacts by threat (highest first)
    const scored = contacts.map((c) => ({
      contact: c,
      score: this._calculateThreatScore(c),
    }));
    scored.sort((a, b) => b.score - a.score);

    list.innerHTML = scored
      .map(({ contact, score }) => this._renderRow(contact, score, lockedId))
      .join("");
  }

  _renderRow(contact, score, lockedId) {
    const id = contact.contact_id || contact.id || "???";
    const classification = contact.classification || contact.class || "UNKNOWN";
    const range = contact.range ?? contact.distance ?? 0;
    const rangeRate = contact.range_rate ?? contact.closure ?? 0;
    const faction = (contact.faction || contact.iff || "unknown").toLowerCase();

    const tier = this._getThreatTier(score);
    const envelope = this._getEnvelopeStatus(range);
    const isLocked = id === lockedId;
    const isSelected = id === this._selectedContact;

    // Closure display
    const closureAbs = Math.abs(rangeRate);
    let closureClass, closureArrow;
    if (rangeRate < 0) {
      closureClass = "closing";
      closureArrow = "v "; // down-arrow indicates closing
    } else if (rangeRate > 0) {
      closureClass = "opening";
      closureArrow = "^ "; // up-arrow indicates opening
    } else {
      closureClass = "stable";
      closureArrow = "  ";
    }

    // Determine if we should show the quick-lock action:
    // Contact is selected, hostile, and not already locked
    const showQuickLock = isSelected && faction === "hostile" && !isLocked;

    return `
      <div class="threat-row ${isLocked ? "locked" : ""}" data-contact-id="${id}">
        <div class="threat-bar ${tier}"></div>
        <div class="row-content">
          <span class="contact-id ${faction}">${id.length > 7 ? id.substring(0, 7) : id}</span>
          <span class="contact-class">${classification.length > 8 ? classification.substring(0, 8) : classification}</span>
          <span class="contact-range">${this._formatRange(range)}</span>
          <span class="contact-closure ${closureClass}">${closureArrow}${this._formatSpeed(closureAbs)}</span>
          <span class="envelope-tag ${envelope.cls}">${envelope.text}</span>
          <span class="lock-icon">${isLocked ? "+" : ""}</span>
        </div>
      </div>
      <div class="quick-lock ${showQuickLock ? "visible" : ""}" data-contact-id="${id}">
        <button class="quick-lock-btn" data-contact="${id}">LOCK TARGET</button>
        <span class="quick-lock-label">Hostile contact - not locked</span>
      </div>
    `;
  }

  _formatRange(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(1)}km`;
    }
    return `${meters.toFixed(0)}m`;
  }

  _formatSpeed(metersPerSecond) {
    if (metersPerSecond >= 1000) {
      return `${(metersPerSecond / 1000).toFixed(1)}km/s`;
    }
    return `${metersPerSecond.toFixed(0)}m/s`;
  }
}

customElements.define("threat-board", ThreatBoard);
export { ThreatBoard };
