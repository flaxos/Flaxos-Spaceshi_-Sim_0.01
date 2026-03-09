/**
 * Power Profile Selector
 * Lets the Engineering station select and apply predefined power profiles.
 * Fetches available profiles from the server and polls for state changes.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

class PowerProfileSelector extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._profiles = [];
    this._currentProfile = null;
    this._selectedProfile = null;
    this._pollInterval = null;
    this._unsubscribe = null;
  }

  connectedCallback() {
    this._render();
    this._fetchProfiles();
    this._pollInterval = setInterval(() => this._fetchProfiles(), 10000);
    this._unsubscribe = stateManager.subscribe("power", (state) => {
      if (state?.active_profile && state.active_profile !== this._currentProfile) {
        this._currentProfile = state.active_profile;
        this._selectedProfile = this._currentProfile;
        this._updateCards();
      }
    });
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
  }

  async _fetchProfiles() {
    try {
      const result = await wsClient.sendShipCommand("get_power_profiles", {});
      if (result?.profiles) {
        this._profiles = result.profiles;
      }
      if (result?.active_profile) {
        this._currentProfile = result.active_profile;
        // Only sync selection if user hasn't picked something else
        if (!this._selectedProfile) {
          this._selectedProfile = this._currentProfile;
        }
      }
      this._updateCards();
    } catch (err) {
      console.error("Failed to fetch power profiles:", err);
    }
  }

  async _applyProfile(name) {
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (applyBtn) {
      applyBtn.disabled = true;
      applyBtn.textContent = "APPLYING...";
    }
    try {
      await wsClient.sendShipCommand("set_power_profile", { profile: name });
      this._currentProfile = name;
      this._selectedProfile = name;
      this._updateCards();
    } catch (err) {
      console.error("Failed to apply power profile:", err);
    } finally {
      if (applyBtn) {
        applyBtn.disabled = false;
        applyBtn.textContent = "APPLY";
      }
    }
  }

  _updateCards() {
    const container = this.shadowRoot.getElementById("profile-list");
    if (!container) return;

    container.innerHTML = this._profiles.map(p => `
      <div class="profile-card ${p.name === this._currentProfile ? "active" : ""}
           ${p.name === this._selectedProfile ? "selected" : ""}"
           data-profile="${p.name}">
        <div class="profile-name">${p.name.toUpperCase()}</div>
        <div class="profile-desc">${p.description || ""}</div>
      </div>
    `).join("");

    container.querySelectorAll(".profile-card").forEach(card => {
      card.addEventListener("click", () => {
        this._selectedProfile = card.dataset.profile;
        this._updateCards();
      });
    });

    // Update apply button state
    const applyBtn = this.shadowRoot.getElementById("apply-btn");
    if (applyBtn) {
      const canApply = this._selectedProfile
        && this._selectedProfile !== this._currentProfile;
      applyBtn.disabled = !canApply;
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .header {
          font-size: 0.75rem;
          font-weight: 600;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: var(--text-secondary, #a0a0b0);
          margin-bottom: 10px;
        }

        #profile-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 12px;
        }

        .profile-card {
          padding: 10px 12px;
          background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          cursor: pointer;
          transition: border-color 0.15s ease, background 0.15s ease;
        }

        .profile-card:hover {
          background: #1e1e34;
        }

        .profile-card.selected {
          border-color: var(--status-info, #4488ff);
        }

        .profile-card.active {
          border-color: var(--status-nominal, #00ff88);
          box-shadow: inset 0 0 8px rgba(0, 255, 136, 0.06);
        }

        /* Selected overrides active border when picking a new profile */
        .profile-card.selected:not(.active) {
          border-color: var(--status-info, #4488ff);
        }

        .profile-name {
          font-size: 0.8rem;
          font-weight: 700;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 2px;
        }

        .profile-card.active .profile-name {
          color: var(--status-nominal, #00ff88);
        }

        .profile-desc {
          font-size: 0.7rem;
          color: var(--text-dim, #666680);
          line-height: 1.3;
        }

        #apply-btn {
          width: 100%;
          padding: 8px 0;
          background: transparent;
          border: 1px solid var(--status-nominal, #00ff88);
          border-radius: 6px;
          color: var(--status-nominal, #00ff88);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 700;
          letter-spacing: 2px;
          cursor: pointer;
          transition: background 0.15s ease, opacity 0.15s ease;
        }

        #apply-btn:hover:not(:disabled) {
          background: rgba(0, 255, 136, 0.08);
        }

        #apply-btn:disabled {
          opacity: 0.3;
          cursor: default;
        }
      </style>

      <div class="header">Power Profile</div>
      <div id="profile-list"></div>
      <button id="apply-btn" disabled>APPLY</button>
    `;

    this.shadowRoot.getElementById("apply-btn").addEventListener("click", () => {
      if (this._selectedProfile && this._selectedProfile !== this._currentProfile) {
        this._applyProfile(this._selectedProfile);
      }
    });
  }
}

customElements.define("power-profile-selector", PowerProfileSelector);
export { PowerProfileSelector };
