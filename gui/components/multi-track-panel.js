/**
 * Multi-Target Tracking Panel
 *
 * Displays and manages the multi-track targeting system. Allows the
 * tactical officer to:
 *   - Maintain simultaneous tracks on multiple contacts
 *   - Cycle primary target (Tab key shortcut)
 *   - Assign individual PDC turrets to specific threats
 *   - Split-fire weapons across different targets
 *
 * Telemetry path: ship.targeting.multi_track
 *   { track_count, base_max_tracks, tracks[], primary_target,
 *     pdc_assignments{}, split_fire_assignments{} }
 *
 * Server commands: add_track, remove_track, cycle_target,
 *   assign_pdc_target, split_fire, clear_assignments, track_list
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class MultiTrackPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._contactSelectedHandler = null;
    this._keydownHandler = null;
    this._selectedContact = null;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();

    // Listen for contact-selected events from sensor panel
    this._contactSelectedHandler = (e) => {
      this._selectedContact = e.detail.contactId;
      this._updateAddButton();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);

    // Tab key shortcut for cycling target
    this._keydownHandler = (e) => {
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey && !e.metaKey) {
        // Only intercept Tab if we have 2+ tracks and the tactical view is active
        const tacticalView = document.getElementById("view-tactical");
        if (tacticalView?.classList.contains("active")) {
          e.preventDefault();
          this._cycleTarget();
        }
      }
    };
    document.addEventListener("keydown", this._keydownHandler);
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
    }
    if (this._keydownHandler) {
      document.removeEventListener("keydown", this._keydownHandler);
      this._keydownHandler = null;
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

        /* -- Track List -- */
        .track-list {
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .track-count {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          color: var(--text-dim, #555566);
        }

        .track-entry {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 10px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          margin-bottom: 4px;
          transition: border-color 0.15s ease;
        }

        .track-entry.primary {
          border-color: var(--status-info, #00aaff);
          background: rgba(0, 170, 255, 0.06);
        }

        .track-priority {
          width: 20px;
          height: 20px;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.65rem;
          font-weight: 700;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          flex-shrink: 0;
        }

        .track-priority.pri-0 {
          background: rgba(0, 170, 255, 0.2);
          color: var(--status-info, #00aaff);
        }

        .track-priority.pri-1,
        .track-priority.pri-2,
        .track-priority.pri-3 {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-dim, #555566);
        }

        .track-info {
          flex: 1;
          min-width: 0;
        }

        .track-id {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .track-meta {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          display: flex;
          gap: 8px;
          margin-top: 2px;
        }

        .quality-bar {
          width: 40px;
          height: 4px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 2px;
          overflow: hidden;
          flex-shrink: 0;
          align-self: center;
        }

        .quality-fill {
          height: 100%;
          border-radius: 2px;
          transition: width 0.3s ease;
        }

        .quality-fill.high { background: var(--status-nominal, #00ff88); }
        .quality-fill.mid { background: var(--status-warning, #ffaa00); }
        .quality-fill.low { background: var(--status-critical, #ff4444); }

        .remove-btn {
          width: 24px;
          height: 24px;
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          background: transparent;
          color: var(--text-dim, #555566);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.75rem;
          flex-shrink: 0;
          transition: all 0.1s ease;
          font-family: inherit;
        }

        .remove-btn:hover {
          background: rgba(255, 68, 68, 0.1);
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .empty-track-msg {
          color: var(--text-dim, #555566);
          font-size: 0.75rem;
          font-style: italic;
          text-align: center;
          padding: 16px;
        }

        /* -- Track Actions (Add / Cycle) -- */
        .track-actions {
          display: flex;
          gap: 6px;
          margin-bottom: 16px;
        }

        .action-btn {
          flex: 1;
          padding: 10px 12px;
          border-radius: 6px;
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.1s ease;
          min-height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
        }

        .add-track-btn {
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .add-track-btn:hover:not(:disabled) {
          background: rgba(0, 170, 255, 0.15);
        }

        .add-track-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        .cycle-btn {
          background: rgba(0, 255, 136, 0.08);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .cycle-btn:hover:not(:disabled) {
          background: rgba(0, 255, 136, 0.15);
        }

        .cycle-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }

        /* -- Weapon Assignments Section -- */
        .assignments-section {
          border-top: 1px solid var(--border-default, #2a2a3a);
          padding-top: 12px;
          margin-top: 4px;
        }

        .assignment-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 6px;
        }

        .mount-label {
          font-size: 0.7rem;
          font-weight: 600;
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          width: 70px;
          flex-shrink: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .assign-select {
          flex: 1;
          padding: 6px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          min-height: 30px;
        }

        .assign-select:focus {
          outline: none;
          border-color: var(--status-info, #00aaff);
        }

        .assign-select option {
          background: var(--bg-input, #1a1a24);
          color: var(--text-primary, #e0e0e0);
        }

        .clear-all-btn {
          width: 100%;
          padding: 8px 12px;
          border: 1px solid var(--status-warning, #ffaa00);
          border-radius: 6px;
          background: transparent;
          color: var(--status-warning, #ffaa00);
          font-family: inherit;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          cursor: pointer;
          transition: background 0.1s ease;
          margin-top: 8px;
          min-height: 34px;
        }

        .clear-all-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .no-weapons-msg {
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          font-style: italic;
          padding: 8px 0;
        }

        .kbd {
          display: inline-block;
          padding: 1px 5px;
          font-size: 0.6rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 3px;
          color: var(--text-dim, #555566);
        }

        .weapons-assigned-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 3px;
          margin-top: 2px;
        }

        .weapon-tag {
          font-size: 0.55rem;
          padding: 1px 4px;
          border-radius: 3px;
          background: rgba(0, 170, 255, 0.12);
          color: var(--status-info, #00aaff);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          text-transform: uppercase;
        }
      </style>

      <!-- Track List -->
      <div class="track-list">
        <div class="section-title">
          <span>Tracked Contacts</span>
          <span class="track-count" id="track-count">0 / 4</span>
        </div>
        <div id="track-entries"></div>
      </div>

      <!-- Add / Cycle Actions -->
      <div class="track-actions">
        <button class="action-btn add-track-btn" id="add-track-btn" disabled
                title="Select a contact from sensor panel first">
          + ADD TRACK
        </button>
        <button class="action-btn cycle-btn" id="cycle-btn" disabled
                title="Cycle primary target (Tab)">
          CYCLE <span class="kbd">Tab</span>
        </button>
      </div>

      <!-- Weapon Assignments -->
      <div class="assignments-section" id="assignments-section">
        <div class="section-title">PDC Assignments</div>
        <div id="pdc-assignments"></div>

        <div class="section-title" style="margin-top: 12px;">Split Fire</div>
        <div id="split-fire-assignments"></div>

        <button class="clear-all-btn" id="clear-all-btn">Clear All Assignments</button>
      </div>
    `;
  }

  _setupInteraction() {
    this.shadowRoot.getElementById("add-track-btn").addEventListener("click", () => {
      this._addTrack();
    });

    this.shadowRoot.getElementById("cycle-btn").addEventListener("click", () => {
      this._cycleTarget();
    });

    this.shadowRoot.getElementById("clear-all-btn").addEventListener("click", () => {
      this._clearAssignments();
    });
  }

  _getMultiTrackState() {
    const targeting = stateManager.getTargeting();
    return targeting?.multi_track || null;
  }

  _updateDisplay() {
    const mt = this._getMultiTrackState();
    const tracks = mt?.tracks || [];
    const maxTracks = mt?.base_max_tracks || 4;
    const primaryTarget = mt?.primary_target || null;
    const pdcAssignments = mt?.pdc_assignments || {};
    const splitAssignments = mt?.split_fire_assignments || {};

    // Track count
    const countEl = this.shadowRoot.getElementById("track-count");
    countEl.textContent = `${tracks.length} / ${maxTracks}`;

    // Track entries
    this._renderTrackEntries(tracks, primaryTarget, pdcAssignments, splitAssignments);

    // Cycle button state: need 2+ tracks
    const cycleBtn = this.shadowRoot.getElementById("cycle-btn");
    cycleBtn.disabled = tracks.length < 2;
    cycleBtn.title = tracks.length < 2
      ? "Need 2+ tracked targets to cycle"
      : "Cycle primary target (Tab)";

    // Add button state
    this._updateAddButton();

    // Weapon assignment dropdowns
    this._renderWeaponAssignments(tracks, pdcAssignments, splitAssignments);
  }

  _renderTrackEntries(tracks, primaryTarget, pdcAssignments, splitAssignments) {
    const container = this.shadowRoot.getElementById("track-entries");

    if (tracks.length === 0) {
      container.innerHTML = `
        <div class="empty-track-msg">
          No contacts tracked. Select a contact and click Add Track.
        </div>
      `;
      return;
    }

    // Build a map of weapon assignments per contact for display
    const weaponsByContact = {};
    for (const [mount, cid] of Object.entries(pdcAssignments)) {
      if (!weaponsByContact[cid]) weaponsByContact[cid] = [];
      weaponsByContact[cid].push(mount);
    }
    for (const [mount, cid] of Object.entries(splitAssignments)) {
      if (!weaponsByContact[cid]) weaponsByContact[cid] = [];
      // Avoid duplicates if same mount in both dicts
      if (!weaponsByContact[cid].includes(mount)) {
        weaponsByContact[cid].push(mount);
      }
    }

    let html = "";
    for (const track of tracks) {
      const isPrimary = track.contact_id === primaryTarget;
      const qualPct = Math.round((track.quality_modifier || 0) * 100);
      const qualClass = qualPct >= 70 ? "high" : qualPct >= 40 ? "mid" : "low";
      const assignedWeapons = weaponsByContact[track.contact_id] || [];

      html += `
        <div class="track-entry ${isPrimary ? "primary" : ""}" data-contact="${track.contact_id}">
          <div class="track-priority pri-${track.priority}">
            ${isPrimary ? "P" : track.priority}
          </div>
          <div class="track-info">
            <div class="track-id">${track.contact_id}</div>
            <div class="track-meta">
              <span>Q:${qualPct}%</span>
              ${assignedWeapons.length > 0
                ? `<span>${assignedWeapons.length} wpn</span>`
                : ""}
            </div>
            ${assignedWeapons.length > 0 ? `
              <div class="weapons-assigned-tags">
                ${assignedWeapons.map(w => `<span class="weapon-tag">${this._shortMount(w)}</span>`).join("")}
              </div>
            ` : ""}
          </div>
          <div class="quality-bar">
            <div class="quality-fill ${qualClass}" style="width: ${qualPct}%"></div>
          </div>
          <button class="remove-btn" data-remove="${track.contact_id}" title="Remove track">X</button>
        </div>
      `;
    }

    container.innerHTML = html;

    // Bind remove handlers
    container.querySelectorAll(".remove-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._removeTrack(btn.dataset.remove);
      });
    });
  }

  _renderWeaponAssignments(tracks, pdcAssignments, splitAssignments) {
    const weapons = stateManager.getWeapons();
    const truthWeapons = weapons?.truth_weapons || {};
    const trackIds = tracks.map((t) => t.contact_id);

    // PDC mounts
    const pdcContainer = this.shadowRoot.getElementById("pdc-assignments");
    const pdcMounts = Object.keys(truthWeapons).filter((id) => id.startsWith("pdc"));

    if (pdcMounts.length === 0 || trackIds.length === 0) {
      pdcContainer.innerHTML = trackIds.length === 0
        ? '<div class="no-weapons-msg">Add tracks to assign weapons</div>'
        : '<div class="no-weapons-msg">No PDC mounts available</div>';
    } else {
      let html = "";
      for (const mount of pdcMounts) {
        const assigned = pdcAssignments[mount] || "";
        html += `
          <div class="assignment-row">
            <span class="mount-label">${this._shortMount(mount)}</span>
            <select class="assign-select" data-pdc-mount="${mount}">
              <option value="">-- primary --</option>
              ${trackIds.map((cid) =>
                `<option value="${cid}" ${cid === assigned ? "selected" : ""}>${cid}</option>`
              ).join("")}
            </select>
          </div>
        `;
      }
      pdcContainer.innerHTML = html;

      // Bind PDC assignment change handlers
      pdcContainer.querySelectorAll("select").forEach((sel) => {
        sel.addEventListener("change", () => {
          const mount = sel.dataset.pdcMount;
          const contactId = sel.value;
          if (contactId) {
            this._assignPdc(mount, contactId);
          }
          // Empty value = revert to primary (clear via clear_assignments)
        });
      });
    }

    // Split fire (railguns and other non-PDC mounts)
    const splitContainer = this.shadowRoot.getElementById("split-fire-assignments");
    const nonPdcMounts = Object.keys(truthWeapons).filter((id) => !id.startsWith("pdc"));

    if (nonPdcMounts.length === 0 || trackIds.length === 0) {
      splitContainer.innerHTML = trackIds.length === 0
        ? ""
        : '<div class="no-weapons-msg">No split-fire mounts available</div>';
    } else {
      let html = "";
      for (const mount of nonPdcMounts) {
        const assigned = splitAssignments[mount] || "";
        html += `
          <div class="assignment-row">
            <span class="mount-label">${this._shortMount(mount)}</span>
            <select class="assign-select" data-split-mount="${mount}">
              <option value="">-- primary --</option>
              ${trackIds.map((cid) =>
                `<option value="${cid}" ${cid === assigned ? "selected" : ""}>${cid}</option>`
              ).join("")}
            </select>
          </div>
        `;
      }
      splitContainer.innerHTML = html;

      // Bind split-fire change handlers
      splitContainer.querySelectorAll("select").forEach((sel) => {
        sel.addEventListener("change", () => {
          const mount = sel.dataset.splitMount;
          const contactId = sel.value;
          if (contactId) {
            this._splitFire(mount, contactId);
          }
        });
      });
    }
  }

  _updateAddButton() {
    const addBtn = this.shadowRoot.getElementById("add-track-btn");
    if (!addBtn) return;

    const mt = this._getMultiTrackState();
    const trackCount = mt?.tracks?.length || 0;
    const maxTracks = mt?.base_max_tracks || 4;
    const alreadyTracking = (mt?.tracks || []).some(
      (t) => t.contact_id === this._selectedContact
    );

    const canAdd = this._selectedContact && !alreadyTracking && trackCount < maxTracks;
    addBtn.disabled = !canAdd;

    if (!this._selectedContact) {
      addBtn.title = "Select a contact from sensor panel first";
    } else if (alreadyTracking) {
      addBtn.title = `${this._selectedContact} is already tracked`;
    } else if (trackCount >= maxTracks) {
      addBtn.title = `Track list full (${maxTracks} max)`;
    } else {
      addBtn.title = `Add ${this._selectedContact} to track list`;
    }
  }

  /** Shorten mount names for display: "railgun_1" -> "RG 1", "pdc_2" -> "PDC 2" */
  _shortMount(mountId) {
    return mountId
      .replace("railgun_", "RG ")
      .replace("pdc_", "PDC ")
      .replace("torpedo_", "TRP ")
      .toUpperCase();
  }

  // -- Server command wrappers --

  async _addTrack() {
    if (!this._selectedContact) return;
    try {
      await wsClient.sendShipCommand("add_track", {
        contact_id: this._selectedContact,
      });
    } catch (err) {
      console.error("add_track failed:", err);
    }
  }

  async _removeTrack(contactId) {
    try {
      await wsClient.sendShipCommand("remove_track", {
        contact_id: contactId,
      });
    } catch (err) {
      console.error("remove_track failed:", err);
    }
  }

  async _cycleTarget() {
    try {
      await wsClient.sendShipCommand("cycle_target", {});
    } catch (err) {
      console.error("cycle_target failed:", err);
    }
  }

  async _assignPdc(mountId, contactId) {
    try {
      await wsClient.sendShipCommand("assign_pdc_target", {
        mount_id: mountId,
        contact_id: contactId,
      });
    } catch (err) {
      console.error("assign_pdc_target failed:", err);
    }
  }

  async _splitFire(mountId, contactId) {
    try {
      await wsClient.sendShipCommand("split_fire", {
        mount_id: mountId,
        contact_id: contactId,
      });
    } catch (err) {
      console.error("split_fire failed:", err);
    }
  }

  async _clearAssignments() {
    try {
      await wsClient.sendShipCommand("clear_assignments", {});
    } catch (err) {
      console.error("clear_assignments failed:", err);
    }
  }
}

customElements.define("multi-track-panel", MultiTrackPanel);
export { MultiTrackPanel };
