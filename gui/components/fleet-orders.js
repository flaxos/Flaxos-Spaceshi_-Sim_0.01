/**
 * Fleet Orders -- maneuver command panel.
 * Tier-aware:
 *   MANUAL: hidden via CSS (no command authority)
 *   RAW:    full maneuver list with coordinate input
 *   ARCADE: preset maneuver buttons (Attack/Defend/Escort/Retreat)
 *   CPU-ASSIST: auto-fleet proposal cards (approve/deny)
 */

import { wsClient } from "../js/ws-client.js";
import { getProposalCSS } from "../js/proposal-styles.js";

// RAW tier: full maneuver set with technical labels
const RAW_MANEUVERS = [
  { id: "intercept", label: "INTERCEPT", desc: "Pursue and engage target", color: "#ffaa00" },
  { id: "match_velocity", label: "MATCH VEL", desc: "Match target velocity vector", color: "#4488ff" },
  { id: "hold", label: "HOLD POS", desc: "Maintain current position", color: "#00ff88" },
  { id: "evasive", label: "EVASIVE", desc: "Random evasive maneuvers", color: "#ff4444" },
];

// ARCADE tier: simplified preset maneuvers with player-friendly labels
const ARCADE_MANEUVERS = [
  { id: "intercept", label: "ATTACK", desc: "Engage designated target", color: "#ff4444" },
  { id: "hold", label: "DEFEND", desc: "Hold position, weapons free", color: "#4488ff" },
  { id: "match_velocity", label: "ESCORT", desc: "Match velocity with ally", color: "#00ff88" },
  { id: "evasive", label: "RETREAT", desc: "Disengage and evade", color: "#ffaa00" },
];

class FleetOrders extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._active = null;
    this._pulseInterval = null;
    this._tier = window.controlTier || "arcade";
    this._tierHandler = null;
    this._proposals = [];
    this._proposalPollInterval = null;
  }

  connectedCallback() {
    this._tier = window.controlTier || "arcade";
    this._render();
    this._bind();

    // Listen for tier changes
    this._tierHandler = (e) => {
      const newTier = e.detail?.tier;
      if (newTier && newTier !== this._tier) {
        this._tier = newTier;
        this._render();
        this._bind();
      }
    };
    document.addEventListener("tier-change", this._tierHandler);

    // CPU-ASSIST: poll auto-fleet proposals
    if (this._tier === "cpu-assist") {
      this._startProposalPolling();
    }
  }

  disconnectedCallback() {
    clearInterval(this._pulseInterval);
    this._pulseInterval = null;
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
    this._stopProposalPolling();
  }

  _getManeuvers() {
    if (this._tier === "arcade") return ARCADE_MANEUVERS;
    return RAW_MANEUVERS;
  }

  _render() {
    if (this._tier === "cpu-assist") {
      this._renderProposals();
      return;
    }

    const maneuvers = this._getManeuvers();
    const buttons = maneuvers.map(m => `
      <button class="btn" data-maneuver="${m.id}" style="--btn-color: ${m.color}">
        <span class="btn-label">${m.label}</span>
        <span class="btn-desc">${m.desc}</span>
      </button>
    `).join("");

    // RAW tier gets an optional coordinate input section
    const coordSection = this._tier === "raw" ? `
      <div class="coord-section">
        <div class="coord-label">Target Coordinates (optional)</div>
        <div class="coord-inputs">
          <input type="number" class="coord" id="coord-x" placeholder="X (km)" step="0.1">
          <input type="number" class="coord" id="coord-y" placeholder="Y (km)" step="0.1">
          <input type="number" class="coord" id="coord-z" placeholder="Z (km)" step="0.1">
        </div>
      </div>
    ` : "";

    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._coordStyles()}</style>
      <div class="status">Maneuver: <span id="current">NONE</span></div>
      ${coordSection}
      <div class="grid">${buttons}</div>
    `;
  }

  _renderProposals() {
    const cards = this._proposals.length > 0
      ? this._proposals.map(p => {
        const confidence = p.confidence ?? 0;
        const remaining = Math.max(0, p.time_remaining || 0);
        const total = p.total_time || 30;
        const timerPct = Math.min(100, (remaining / total) * 100);
        const isUrgent = confidence > 0.8 || remaining < 5;
        const urgentClass = isUrgent ? " urgent" : "";
        const countdownClass = remaining < 5 ? " expiring" : "";
        return `
        <div class="proposal-card${urgentClass}">
          <div class="proposal-header">
            <span class="proposal-action">${this._esc(p.proposal_id)}</span>
            <span class="proposal-confidence">${(confidence * 100).toFixed(0)}%</span>
            ${p.crew_efficiency != null ? `<span class="proposal-crew">Crew: ${(p.crew_efficiency * 100).toFixed(0)}%</span>` : ""}
          </div>
          <div class="proposal-reason">${this._esc(p.reason)}</div>
          <div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>
          ${p.auto_execute ? `<div class="proposal-countdown${countdownClass}" style="font-size:0.65rem;margin-bottom:6px;">Auto-execute in ${Math.ceil(remaining)}s</div>` : ""}
          <div class="proposal-actions">
            <button class="btn-approve" data-id="${this._esc(p.proposal_id)}">APPROVE</button>
            <button class="btn-deny" data-id="${this._esc(p.proposal_id)}">DENY</button>
          </div>
        </div>`;
      }).join("")
      : '<div class="no-proposals">Auto-fleet monitoring -- no proposals</div>';

    this.shadowRoot.innerHTML = `
      <style>${this._baseStyles()}${this._proposalStyles()}</style>
      <div class="auto-header">
        <span class="auto-label">AUTO-FLEET PROPOSALS</span>
        <button class="btn-toggle" id="toggle-auto">${this._proposals.length > 0 ? "DISABLE" : "ENABLE"}</button>
      </div>
      <div class="proposals">${cards}</div>
    `;
  }

  _bind() {
    if (this._tier === "cpu-assist") {
      // Proposal approve/deny buttons
      this.shadowRoot.querySelectorAll(".btn-approve").forEach(btn => {
        btn.addEventListener("click", () => this._approveProposal(btn.dataset.id));
      });
      this.shadowRoot.querySelectorAll(".btn-deny").forEach(btn => {
        btn.addEventListener("click", () => this._denyProposal(btn.dataset.id));
      });
      const toggle = this.shadowRoot.getElementById("toggle-auto");
      if (toggle) {
        toggle.addEventListener("click", () => this._toggleAutoFleet());
      }
      this._startProposalPolling();
      return;
    }

    this._stopProposalPolling();
    this.shadowRoot.querySelectorAll(".btn").forEach(btn => {
      btn.addEventListener("click", () => this._execute(btn.dataset.maneuver));
    });
  }

  async _execute(maneuver) {
    const fleetId = this.getAttribute("fleet-id") || "default";
    const params = {
      fleet_id: fleetId,
      maneuver,
      position: null,
      velocity: null,
    };

    // RAW tier: read coordinate inputs if present
    if (this._tier === "raw") {
      const x = this.shadowRoot.getElementById("coord-x")?.value;
      const y = this.shadowRoot.getElementById("coord-y")?.value;
      const z = this.shadowRoot.getElementById("coord-z")?.value;
      if (x || y || z) {
        params.position = [
          parseFloat(x || 0) * 1000,
          parseFloat(y || 0) * 1000,
          parseFloat(z || 0) * 1000,
        ];
      }
    }

    try {
      await wsClient.sendShipCommand("fleet_maneuver", params);
      this._setActive(maneuver);
    } catch (err) {
      console.error("Fleet maneuver failed:", err);
    }
  }

  _setActive(maneuver) {
    this._active = maneuver;
    const maneuvers = this._getManeuvers();
    const meta = maneuvers.find(m => m.id === maneuver);
    const el = this.shadowRoot.getElementById("current");
    if (el) el.textContent = meta ? meta.label : "NONE";
    this.shadowRoot.querySelectorAll(".btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.maneuver === maneuver);
    });
  }

  // -- CPU-ASSIST proposal handling --

  _startProposalPolling() {
    this._stopProposalPolling();
    this._pollProposals();
    this._proposalPollInterval = setInterval(() => this._pollProposals(), 3000);
  }

  _stopProposalPolling() {
    if (this._proposalPollInterval) {
      clearInterval(this._proposalPollInterval);
      this._proposalPollInterval = null;
    }
  }

  async _pollProposals() {
    try {
      const res = await wsClient.sendShipCommand("auto_fleet_status", {});
      this._proposals = res?.proposals || [];
      if (this._tier === "cpu-assist") {
        this._renderProposals();
        this._bind();
      }
    } catch {
      // Not connected or system not available
    }
  }

  async _approveProposal(proposalId) {
    try {
      await wsClient.sendShipCommand("approve_fleet", { proposal_id: proposalId });
      this._pollProposals();
    } catch (err) {
      console.error("Fleet proposal approve failed:", err);
    }
  }

  async _denyProposal(proposalId) {
    try {
      await wsClient.sendShipCommand("deny_fleet", { proposal_id: proposalId });
      this._pollProposals();
    } catch (err) {
      console.error("Fleet proposal deny failed:", err);
    }
  }

  async _toggleAutoFleet() {
    try {
      const cmd = this._proposals.length > 0 ? "disable_auto_fleet" : "enable_auto_fleet";
      await wsClient.sendShipCommand(cmd, {});
      this._pollProposals();
    } catch (err) {
      console.error("Auto-fleet toggle failed:", err);
    }
  }

  _esc(str) {
    const d = document.createElement("div");
    d.textContent = str ?? "";
    return d.innerHTML;
  }

  // -- Styles --

  _baseStyles() {
    return `
      :host {
        display: block;
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 6px;
        padding: 12px;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }
      .status {
        font-size: 0.75rem;
        color: var(--text-dim, #666680);
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .status span {
        color: var(--text-primary, #e0e0e0);
      }
      .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }
      .btn {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 4px;
        padding: 14px 8px;
        background: var(--bg-input, #1a1a2e);
        border: 2px solid var(--border-default, #2a2a3a);
        border-radius: 6px;
        cursor: pointer;
        transition: border-color 0.15s, background 0.15s;
      }
      .btn:hover {
        border-color: var(--btn-color);
        background: color-mix(in srgb, var(--btn-color) 8%, var(--bg-input, #1a1a2e));
      }
      .btn.active {
        border-color: var(--btn-color);
        animation: pulse 1.5s ease-in-out infinite;
      }
      .btn-label {
        font-size: 0.85rem;
        font-weight: 700;
        color: var(--btn-color);
      }
      .btn-desc {
        font-size: 0.65rem;
        color: var(--text-secondary, #a0a0b0);
      }
      @keyframes pulse {
        0%, 100% { box-shadow: 0 0 0 0 transparent; }
        50% { box-shadow: 0 0 8px 2px var(--btn-color); }
      }
    `;
  }

  _coordStyles() {
    return `
      .coord-section {
        margin-bottom: 10px;
        padding: 8px;
        background: var(--bg-input, #1a1a2e);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
      }
      .coord-label {
        font-size: 0.65rem;
        color: var(--text-dim, #666680);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
      }
      .coord-inputs {
        display: flex;
        gap: 6px;
      }
      .coord {
        flex: 1;
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 3px;
        padding: 4px 6px;
        color: var(--text-primary, #e0e0e0);
        font-family: inherit;
        font-size: 0.75rem;
      }
      .coord:focus {
        border-color: var(--status-info, #4488ff);
        outline: none;
      }
    `;
  }

  _proposalStyles() {
    return `
      .auto-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border-default, #2a2a3a);
      }
      .auto-label {
        font-size: 0.7rem;
        color: var(--tier-accent, #c0a0ff);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 700;
      }
      .btn-toggle {
        background: var(--bg-input, #1a1a2e);
        border: 1px solid var(--tier-accent, #c0a0ff);
        color: var(--tier-accent, #c0a0ff);
        padding: 3px 10px;
        border-radius: 3px;
        font-family: inherit;
        font-size: 0.65rem;
        cursor: pointer;
        text-transform: uppercase;
      }
      .btn-toggle:hover {
        background: rgba(192, 160, 255, 0.1);
      }
      /* Proposal cards — shared styles from proposal-styles.js */
      ${getProposalCSS()}
      .proposal-id {
        font-size: 0.65rem;
        color: var(--text-dim, #666680);
        font-weight: 600;
      }
    `;
  }
}

customElements.define("fleet-orders", FleetOrders);
export { FleetOrders };
