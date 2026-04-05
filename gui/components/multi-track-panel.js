/**
 * Multi-Target Tracking Panel
 *
 * Displays and manages the multi-track targeting system with inline
 * weapon assignment. Each tracked contact renders as a card with:
 *   - Contact ID + classification, bearing + range
 *   - Track quality bar (color-coded)
 *   - Lock state icon
 *   - Inline PDC toggle buttons and split-fire weapon dropdown
 *   - PRIMARY badge on first track
 *
 * PDC defense mode status shown at top of panel.
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
    this._lastUpdateTime = 0;
    this._lastTrackJson = "";
    this._updatePending = false;
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();

    this._contactSelectedHandler = (e) => {
      this._selectedContact = e.detail.contactId;
      this._updateAddButton();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);

    this._keydownHandler = (e) => {
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey && !e.metaKey) {
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
      const now = performance.now();
      if (now - this._lastUpdateTime < 200) {
        if (!this._updatePending) {
          this._updatePending = true;
          setTimeout(() => {
            this._updatePending = false;
            this._lastUpdateTime = performance.now();
            this._updateDisplay();
          }, 200);
        }
        return;
      }
      this._lastUpdateTime = now;
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${MultiTrackPanel.styles()}
      </style>

      <!-- PDC Mode Status -->
      <div class="pdc-mode-bar" id="pdc-mode-bar">
        <span class="pdc-mode-label">PDC MODE</span>
        <span class="pdc-mode-value" id="pdc-mode-value">AUTO</span>
      </div>

      <!-- Track header -->
      <div class="track-header">
        <span class="track-header-title">Tracked Contacts</span>
        <span class="track-count" id="track-count">0 / 4</span>
      </div>

      <!-- Track cards container -->
      <div id="track-cards"></div>

      <!-- Actions -->
      <div class="track-actions">
        <button class="action-btn add-btn" id="add-track-btn" disabled
                title="Select a contact from sensor panel first">
          + ADD
        </button>
        <button class="action-btn cycle-btn" id="cycle-btn" disabled
                title="Cycle primary target (Tab)">
          CYCLE <span class="kbd">Tab</span>
        </button>
      </div>
    `;
  }

  /** All CSS for the component, extracted for readability */
  static styles() {
    return `
      :host {
        display: block;
        padding: 12px;
        font-family: var(--font-sans, "Inter", sans-serif);
      }

      /* --- PDC Mode Bar --- */
      .pdc-mode-bar {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        margin-bottom: 10px;
        background: rgba(0, 0, 0, 0.3);
        border-radius: 6px;
        border-left: 3px solid var(--domain-weapons, #cc4444);
      }
      .pdc-mode-label {
        font-size: 0.6rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-dim, #555566);
      }
      .pdc-mode-value {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--domain-weapons, #cc4444);
        text-transform: uppercase;
      }
      .pdc-mode-value.network {
        color: var(--status-info, #00aaff);
      }
      .pdc-engage-info {
        font-size: 0.55rem;
        color: var(--text-dim, #555566);
        margin-left: auto;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
      }

      /* --- Track header --- */
      .track-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      .track-header-title {
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-secondary, #888899);
      }
      .track-count {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.65rem;
        color: var(--text-dim, #555566);
      }

      /* --- Track card --- */
      .track-card {
        padding: 10px;
        margin-bottom: 6px;
        background: var(--bg-input, #1a1a24);
        border: 1px solid var(--border-default, #2a2a3a);
        border-left: 3px solid var(--border-default, #2a2a3a);
        border-radius: 6px;
        transition: border-color 0.15s ease;
      }
      .track-card.primary {
        border-left-color: var(--status-info, #00aaff);
        background: rgba(0, 170, 255, 0.04);
      }

      .card-top {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
      }

      .lock-icon {
        font-size: 0.8rem;
        flex-shrink: 0;
        width: 16px;
        text-align: center;
      }
      .lock-icon.tracking { color: var(--status-warning, #ffaa00); }
      .lock-icon.acquiring { color: var(--status-info, #00aaff); }
      .lock-icon.locked { color: var(--status-nominal, #00ff88); }

      .card-id {
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--text-primary, #e0e0e0);
        flex: 1;
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .primary-badge {
        font-size: 0.5rem;
        font-weight: 700;
        padding: 2px 5px;
        border-radius: 3px;
        background: rgba(0, 170, 255, 0.15);
        color: var(--status-info, #00aaff);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        flex-shrink: 0;
      }

      .remove-btn {
        width: 22px;
        height: 22px;
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 4px;
        background: transparent;
        color: var(--text-dim, #555566);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        flex-shrink: 0;
        transition: all 0.1s ease;
        font-family: inherit;
      }
      .remove-btn:hover {
        background: rgba(255, 68, 68, 0.1);
        border-color: var(--status-critical, #ff4444);
        color: var(--status-critical, #ff4444);
      }

      /* Bearing + range line */
      .card-meta {
        font-size: 0.65rem;
        color: var(--text-dim, #555566);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-variant-numeric: tabular-nums;
        margin-bottom: 6px;
      }

      /* Track quality bar */
      .quality-row {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 8px;
      }
      .quality-label {
        font-size: 0.55rem;
        font-weight: 600;
        color: var(--text-dim, #555566);
        text-transform: uppercase;
        width: 20px;
        flex-shrink: 0;
      }
      .quality-bar {
        flex: 1;
        height: 6px;
        background: rgba(255, 255, 255, 0.06);
        border-radius: 3px;
        overflow: hidden;
      }
      .quality-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.3s ease;
      }
      .quality-fill.high { background: var(--status-nominal, #00ff88); }
      .quality-fill.mid { background: var(--status-warning, #ffaa00); }
      .quality-fill.low { background: var(--status-critical, #ff4444); }
      .quality-pct {
        font-size: 0.6rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-variant-numeric: tabular-nums;
        color: var(--text-secondary, #888899);
        width: 28px;
        text-align: right;
        flex-shrink: 0;
      }

      /* --- Inline PDC buttons --- */
      .weapon-assign-row {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 4px;
      }

      .pdc-toggle {
        padding: 3px 6px;
        border-radius: 3px;
        border: 1px solid var(--border-default, #2a2a3a);
        background: transparent;
        color: var(--text-dim, #555566);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.55rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.1s ease;
      }
      .pdc-toggle:hover {
        border-color: var(--domain-weapons, #cc4444);
        color: var(--text-primary, #e0e0e0);
      }
      .pdc-toggle.assigned {
        border-color: var(--status-nominal, #00ff88);
        color: var(--status-nominal, #00ff88);
        background: rgba(0, 255, 136, 0.08);
      }

      /* --- Inline split-fire select --- */
      .split-select {
        padding: 3px 6px;
        border-radius: 3px;
        border: 1px solid var(--border-default, #2a2a3a);
        background: var(--bg-input, #1a1a24);
        color: var(--text-primary, #e0e0e0);
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.55rem;
        min-height: 22px;
        cursor: pointer;
      }
      .split-select:focus {
        outline: none;
        border-color: var(--status-info, #00aaff);
      }
      .split-select option {
        background: var(--bg-input, #1a1a24);
        color: var(--text-primary, #e0e0e0);
      }

      /* --- Empty state --- */
      .empty-msg {
        color: var(--text-dim, #555566);
        font-size: 0.75rem;
        font-style: italic;
        text-align: center;
        padding: 16px;
      }

      /* --- Action buttons --- */
      .track-actions {
        display: flex;
        gap: 6px;
        margin-top: 10px;
      }
      .action-btn {
        flex: 1;
        padding: 8px 10px;
        border-radius: 6px;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        cursor: pointer;
        transition: all 0.1s ease;
        min-height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
      }
      .add-btn {
        background: rgba(0, 170, 255, 0.08);
        border: 1px solid var(--status-info, #00aaff);
        color: var(--status-info, #00aaff);
      }
      .add-btn:hover:not(:disabled) { background: rgba(0, 170, 255, 0.15); }
      .add-btn:disabled { opacity: 0.35; cursor: not-allowed; }

      .cycle-btn {
        background: rgba(0, 255, 136, 0.08);
        border: 1px solid var(--status-nominal, #00ff88);
        color: var(--status-nominal, #00ff88);
      }
      .cycle-btn:hover:not(:disabled) { background: rgba(0, 255, 136, 0.15); }
      .cycle-btn:disabled { opacity: 0.35; cursor: not-allowed; }

      .kbd {
        display: inline-block;
        padding: 1px 5px;
        font-size: 0.55rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 3px;
        color: var(--text-dim, #555566);
      }

      @media (prefers-reduced-motion: reduce) {
        .quality-fill { transition: none !important; }
        .track-card { transition: none !important; }
      }
    `;
  }

  _setupInteraction() {
    this.shadowRoot.getElementById("add-track-btn").addEventListener("click", () => {
      this._addTrack();
    });
    this.shadowRoot.getElementById("cycle-btn").addEventListener("click", () => {
      this._cycleTarget();
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

    // PDC mode from weapon state
    this._updatePdcMode();

    // Track count
    const countEl = this.shadowRoot.getElementById("track-count");
    if (countEl) countEl.textContent = `${tracks.length} / ${maxTracks}`;

    // Track cards
    this._renderTrackCards(tracks, primaryTarget, pdcAssignments, splitAssignments);

    // Button states
    const cycleBtn = this.shadowRoot.getElementById("cycle-btn");
    if (cycleBtn) {
      cycleBtn.disabled = tracks.length < 2;
      cycleBtn.title = tracks.length < 2
        ? "Need 2+ tracked targets to cycle"
        : "Cycle primary target (Tab)";
    }

    this._updateAddButton();
  }

  _updatePdcMode() {
    const weapons = stateManager.getWeapons();
    const pdcMode = weapons?.pdc_defense_mode || "auto";
    const modeEl = this.shadowRoot.getElementById("pdc-mode-value");
    if (!modeEl) return;

    modeEl.textContent = pdcMode.toUpperCase();
    modeEl.className = `pdc-mode-value ${pdcMode === "network" ? "network" : ""}`;
  }

  _renderTrackCards(tracks, primaryTarget, pdcAssignments, splitAssignments) {
    const container = this.shadowRoot.getElementById("track-cards");
    if (!container) return;

    if (tracks.length === 0) {
      this._lastTrackJson = "";
      container.innerHTML = `
        <div class="empty-msg">
          No contacts tracked. Select a contact and click Add.
        </div>
      `;
      return;
    }

    // Dirty-check: skip rebuild if data hasn't changed
    const trackJson = JSON.stringify({ tracks, primaryTarget, pdcAssignments, splitAssignments });
    if (trackJson === this._lastTrackJson) return;
    this._lastTrackJson = trackJson;

    // If a dropdown is currently open/focused, do in-place updates only
    const activeSelect = this.shadowRoot.activeElement;
    if (activeSelect && activeSelect.classList.contains("split-select")) {
      this._updateCardsInPlace(container, tracks, primaryTarget, pdcAssignments, splitAssignments);
      return;
    }

    const weapons = stateManager.getWeapons();
    const truthWeapons = weapons?.truth_weapons || {};
    const pdcMounts = Object.keys(truthWeapons).filter(id => id.startsWith("pdc"));
    const nonPdcMounts = Object.keys(truthWeapons).filter(id => !id.startsWith("pdc"));

    // Build reverse map: which PDCs are assigned to which contact
    const pdcByContact = {};
    for (const [mount, cid] of Object.entries(pdcAssignments)) {
      if (!pdcByContact[cid]) pdcByContact[cid] = [];
      pdcByContact[cid].push(mount);
    }

    // Build reverse map: which non-PDC weapons are assigned to which contact
    const splitByContact = {};
    for (const [mount, cid] of Object.entries(splitAssignments)) {
      if (!splitByContact[cid]) splitByContact[cid] = [];
      splitByContact[cid].push(mount);
    }

    let html = "";
    for (const track of tracks) {
      const isPrimary = track.contact_id === primaryTarget;
      const qualPct = Math.round((track.quality_modifier || 0) * 100);
      const qualClass = qualPct >= 80 ? "high" : qualPct >= 50 ? "mid" : "low";

      // Lock state icon: use data from track if available, else infer
      const lockState = track.lock_state || "tracking";
      const lockIcon = this._lockIcon(lockState);
      const lockClass = lockState === "locked" ? "locked"
        : lockState === "acquiring" ? "acquiring" : "tracking";

      // Classification from contact data if available
      const classification = track.classification || "";
      const idLine = classification
        ? `${track.contact_id} — ${classification.toUpperCase()}`
        : track.contact_id;

      // Bearing + range
      const bearing = track.bearing != null
        ? `${typeof track.bearing === 'number' ? track.bearing.toFixed(0) : '--'}deg`
        : "--";
      const range = track.range != null ? this._formatRange(track.range) : "--";

      // PDC assignment buttons for this contact
      const assignedPdcs = pdcByContact[track.contact_id] || [];

      // Current split-fire weapon assigned to this contact
      const assignedSplits = splitByContact[track.contact_id] || [];
      // For the dropdown, find which non-PDC weapon targets this contact
      const currentSplitMount = nonPdcMounts.find(m => splitAssignments[m] === track.contact_id) || "";

      html += `
        <div class="track-card ${isPrimary ? 'primary' : ''}" data-contact="${track.contact_id}">
          <div class="card-top">
            <span class="lock-icon ${lockClass}">${lockIcon}</span>
            <span class="card-id">${idLine}</span>
            ${isPrimary ? '<span class="primary-badge">PRIMARY</span>' : ''}
            <button class="remove-btn" data-remove="${track.contact_id}" title="Remove track">X</button>
          </div>

          <div class="card-meta">${bearing} | ${range}</div>

          <div class="quality-row">
            <span class="quality-label">TQ</span>
            <div class="quality-bar">
              <div class="quality-fill ${qualClass}" style="width: ${qualPct}%"></div>
            </div>
            <span class="quality-pct">${qualPct}%</span>
          </div>

          <div class="weapon-assign-row">
            ${pdcMounts.map(mount => {
              const isAssigned = assignedPdcs.includes(mount);
              return `<button class="pdc-toggle ${isAssigned ? 'assigned' : ''}"
                data-pdc-mount="${mount}" data-contact="${track.contact_id}"
                title="${isAssigned ? 'Unassign' : 'Assign'} ${this._shortMount(mount)} to ${track.contact_id}">
                ${this._shortMount(mount)}
              </button>`;
            }).join('')}

            ${nonPdcMounts.length > 0 ? `
              <select class="split-select" data-split-contact="${track.contact_id}"
                title="Assign weapon to fire at ${track.contact_id}">
                <option value="">--</option>
                ${nonPdcMounts.map(m =>
                  `<option value="${m}" ${currentSplitMount === m ? 'selected' : ''}>${this._shortMount(m)}</option>`
                ).join('')}
              </select>
            ` : ''}
          </div>
        </div>
      `;
    }

    container.innerHTML = html;
    this._bindCardHandlers(container);
  }

  /** In-place update when a dropdown is open — avoids destroying the active select */
  _updateCardsInPlace(container, tracks, primaryTarget, pdcAssignments, splitAssignments) {
    for (const track of tracks) {
      const card = container.querySelector(`.track-card[data-contact="${track.contact_id}"]`);
      if (!card) continue;

      // Update primary badge
      const isPrimary = track.contact_id === primaryTarget;
      card.classList.toggle("primary", isPrimary);

      // Update quality bar
      const qualPct = Math.round((track.quality_modifier || 0) * 100);
      const qualClass = qualPct >= 80 ? "high" : qualPct >= 50 ? "mid" : "low";
      const qualFill = card.querySelector(".quality-fill");
      if (qualFill) {
        qualFill.style.width = `${qualPct}%`;
        qualFill.className = `quality-fill ${qualClass}`;
      }
      const qualPctEl = card.querySelector(".quality-pct");
      if (qualPctEl) qualPctEl.textContent = `${qualPct}%`;

      // Update bearing/range
      const metaEl = card.querySelector(".card-meta");
      if (metaEl) {
        const bearing = track.bearing != null
          ? `${typeof track.bearing === 'number' ? track.bearing.toFixed(0) : '--'}deg`
          : "--";
        const range = track.range != null ? this._formatRange(track.range) : "--";
        metaEl.textContent = `${bearing} | ${range}`;
      }

      // Update PDC toggle states
      const pdcByContact = {};
      for (const [mount, cid] of Object.entries(pdcAssignments)) {
        if (!pdcByContact[cid]) pdcByContact[cid] = [];
        pdcByContact[cid].push(mount);
      }
      const assignedPdcs = pdcByContact[track.contact_id] || [];
      card.querySelectorAll(".pdc-toggle").forEach(btn => {
        const isAssigned = assignedPdcs.includes(btn.dataset.pdcMount);
        btn.classList.toggle("assigned", isAssigned);
      });
    }
  }

  /** Bind click/change handlers on newly-rendered card elements */
  _bindCardHandlers(container) {
    // Remove track buttons
    container.querySelectorAll(".remove-btn").forEach(btn => {
      btn.addEventListener("click", () => this._removeTrack(btn.dataset.remove));
    });

    // PDC toggle buttons
    container.querySelectorAll(".pdc-toggle").forEach(btn => {
      btn.addEventListener("click", () => {
        const mount = btn.dataset.pdcMount;
        const contactId = btn.dataset.contact;
        const isAssigned = btn.classList.contains("assigned");
        if (isAssigned) {
          // Unassign: clear this PDC's assignment by assigning to empty
          // Server treats empty contact_id as "revert to primary"
          this._assignPdc(mount, "");
        } else {
          this._assignPdc(mount, contactId);
        }
      });
    });

    // Split-fire dropdowns
    container.querySelectorAll(".split-select").forEach(sel => {
      sel.addEventListener("change", () => {
        const mount = sel.value;
        const contactId = sel.dataset.splitContact;
        if (mount) {
          this._splitFire(mount, contactId);
        }
      });
    });
  }

  _updateAddButton() {
    const addBtn = this.shadowRoot.getElementById("add-track-btn");
    if (!addBtn) return;

    const mt = this._getMultiTrackState();
    const trackCount = mt?.tracks?.length || 0;
    const maxTracks = mt?.base_max_tracks || 4;
    const alreadyTracking = (mt?.tracks || []).some(
      t => t.contact_id === this._selectedContact
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

  // --- Display helpers ---

  _lockIcon(state) {
    // Unicode circles: empty = tracking, half = acquiring, full = locked
    if (state === "locked") return "\u25CF";   // filled circle
    if (state === "acquiring") return "\u25D0"; // half circle
    return "\u25CB";                             // empty circle
  }

  _shortMount(mountId) {
    return mountId
      .replace("railgun_", "RG ")
      .replace("pdc_", "PDC ")
      .replace("torpedo_", "TRP ")
      .replace("missile_", "MSL ")
      .toUpperCase();
  }

  _formatRange(meters) {
    if (meters == null || meters === 0) return "--";
    if (meters >= 1000000) return `${(meters / 1000).toFixed(0)}km`;
    if (meters >= 1000) return `${(meters / 1000).toFixed(1)}km`;
    return `${meters.toFixed(0)}m`;
  }

  // --- Server commands ---

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
