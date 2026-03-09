/**
 * Helm Queue Panel
 * Displays the helm command queue status (active + pending commands)
 * and provides interrupt/clear controls.
 *
 * Subscribes to stateManager for helm queue data via ship state.
 * Falls back to polling helm_queue_status if state data is unavailable.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

class HelmQueuePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pollTimer = null;
    this._queueState = null;
    // Track whether stateManager provides queue data so we know
    // whether to fall back to explicit polling.
    this._stateHasQueueData = false;
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
    this._stopPolling();
  }

  // ---------------------------------------------------------------------------
  // State subscription
  // ---------------------------------------------------------------------------

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", (_value, _key, fullState) => {
      const queue = this._extractQueueFromState(fullState);
      if (queue) {
        this._stateHasQueueData = true;
        this._stopPolling(); // No need to poll if state already provides data
        this._queueState = queue;
        this._updateDisplay();
      } else if (!this._stateHasQueueData && !this._pollTimer) {
        // State does not include queue data — start fallback polling
        this._startPolling();
      }
    });
  }

  /**
   * Try several possible locations for helm queue data in the ship state.
   * Returns { active, pending } or null if not found.
   */
  _extractQueueFromState(fullState) {
    const ship = stateManager.getShipState();
    if (!ship) return null;

    // Primary location: systems.helm.command_queue (from get_state)
    const helmQueue = ship.systems?.helm?.command_queue;
    if (helmQueue && (helmQueue.active !== undefined || helmQueue.pending !== undefined)) {
      return helmQueue;
    }

    // Telemetry location: helm_queue (from station telemetry)
    if (ship.helm_queue && typeof ship.helm_queue === "object") {
      return ship.helm_queue;
    }

    // Alternate: systems.helm.queue
    const altQueue = ship.systems?.helm?.queue;
    if (altQueue && (altQueue.active !== undefined || altQueue.pending !== undefined)) {
      return altQueue;
    }

    return null;
  }

  // ---------------------------------------------------------------------------
  // Fallback polling (every 2 s)
  // ---------------------------------------------------------------------------

  _startPolling() {
    if (this._pollTimer) return;
    this._poll(); // immediate first fetch
    this._pollTimer = setInterval(() => this._poll(), 2000);
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _poll() {
    try {
      const response = await wsClient.sendShipCommand("helm_queue_status", {});
      if (response && response.queue) {
        this._queueState = response.queue;
        this._updateDisplay();
      } else if (response && (response.active !== undefined || response.pending !== undefined)) {
        this._queueState = response;
        this._updateDisplay();
      }
    } catch (_err) {
      // Ignore polling errors — connection may be down
    }
  }

  // ---------------------------------------------------------------------------
  // Commands
  // ---------------------------------------------------------------------------

  async _interruptQueue() {
    try {
      const response = await wsClient.sendShipCommand("interrupt_helm_queue", {});
      if (response?.error) {
        this._showMessage(`Interrupt error: ${response.error}`, "error");
      } else {
        this._showMessage("Helm queue interrupted", "success");
      }
    } catch (error) {
      this._showMessage(`Interrupt failed: ${error.message}`, "error");
    }
  }

  async _clearQueue() {
    try {
      const response = await wsClient.sendShipCommand("clear_helm_queue", {});
      if (response?.error) {
        this._showMessage(`Clear error: ${response.error}`, "error");
      } else {
        this._showMessage("Helm queue cleared", "success");
      }
    } catch (error) {
      this._showMessage(`Clear failed: ${error.message}`, "error");
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

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

        /* Active command display */
        .active-command {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          margin-bottom: 10px;
          background: rgba(0, 255, 136, 0.06);
          border: 1px solid rgba(0, 255, 136, 0.25);
          border-radius: 6px;
          min-height: 40px;
        }

        .active-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--status-nominal, #00ff88);
          flex-shrink: 0;
          animation: pulse-dot 1.8s ease-in-out infinite;
        }

        @keyframes pulse-dot {
          0%, 100% { opacity: 1; box-shadow: 0 0 4px rgba(0, 255, 136, 0.4); }
          50% { opacity: 0.5; box-shadow: 0 0 8px rgba(0, 255, 136, 0.6); }
        }

        .active-info {
          flex: 1;
          min-width: 0;
        }

        .active-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          font-weight: 600;
          color: var(--status-nominal, #00ff88);
        }

        .active-detail {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          margin-top: 2px;
        }

        /* Progress bar for active command */
        .active-progress {
          height: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 2px;
          overflow: hidden;
          margin-top: 6px;
        }

        .active-progress-fill {
          height: 100%;
          background: var(--status-nominal, #00ff88);
          border-radius: 2px;
          transition: width 0.5s ease;
        }

        /* Queue list */
        .queue-list {
          margin-bottom: 12px;
        }

        .queue-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          margin-bottom: 4px;
        }

        .queue-index {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          min-width: 20px;
          text-align: right;
        }

        .queue-item-name {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
          color: var(--text-secondary, #888899);
          flex: 1;
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .queue-item-params {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          max-width: 120px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        /* Queue count badge */
        .queue-count {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-align: right;
          margin-bottom: 8px;
        }

        .queue-count .count-number {
          color: var(--text-primary, #e0e0e0);
          font-weight: 600;
        }

        /* Empty state */
        .empty-state {
          padding: 20px 12px;
          text-align: center;
          color: var(--text-dim, #555566);
          font-size: 0.8rem;
          font-style: italic;
          background: var(--bg-input, #1a1a24);
          border: 1px dashed var(--border-default, #2a2a3a);
          border-radius: 6px;
          margin-bottom: 12px;
        }

        /* Controls */
        .controls {
          display: flex;
          gap: 8px;
        }

        .ctrl-btn {
          flex: 1;
          padding: 10px 8px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-secondary, #888899);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.1s ease;
          min-height: 40px;
        }

        .ctrl-btn:hover:not(:disabled) {
          background: var(--bg-hover, #22222e);
          color: var(--text-primary, #e0e0e0);
        }

        .ctrl-btn:active:not(:disabled) {
          transform: scale(0.96);
        }

        .ctrl-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .ctrl-btn.danger {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .ctrl-btn.danger:hover:not(:disabled) {
          background: rgba(255, 68, 68, 0.15);
          border-color: var(--status-critical, #ff4444);
        }

        .ctrl-btn.warn {
          border-color: var(--status-warning, #ffaa00);
          color: var(--status-warning, #ffaa00);
        }

        .ctrl-btn.warn:hover:not(:disabled) {
          background: rgba(255, 170, 0, 0.12);
          border-color: var(--status-warning, #ffaa00);
        }

        @media (max-width: 768px) {
          :host {
            padding: 10px;
          }

          .controls {
            flex-direction: column;
          }
        }
      </style>

      <div class="section-title">Helm Queue</div>

      <!-- Active command (visible when one is executing) -->
      <div class="active-command" id="active-section" style="display:none;">
        <div class="active-indicator"></div>
        <div class="active-info">
          <div class="active-name" id="active-name">--</div>
          <div class="active-detail" id="active-detail"></div>
          <div class="active-progress" id="active-progress" style="display:none;">
            <div class="active-progress-fill" id="active-progress-fill" style="width:0%"></div>
          </div>
        </div>
      </div>

      <!-- Queue count -->
      <div class="queue-count" id="queue-count" style="display:none;">
        Queued: <span class="count-number" id="count-number">0</span>
      </div>

      <!-- Pending commands list -->
      <div class="queue-list" id="queue-list"></div>

      <!-- Empty state -->
      <div class="empty-state" id="empty-state">No commands queued</div>

      <!-- Controls -->
      <div class="controls">
        <button class="ctrl-btn danger" id="btn-interrupt" disabled>Interrupt</button>
        <button class="ctrl-btn warn" id="btn-clear" disabled>Clear Queue</button>
      </div>
    `;

    // Bind button handlers
    this.shadowRoot.getElementById("btn-interrupt").addEventListener("click", () => {
      this._interruptQueue();
    });
    this.shadowRoot.getElementById("btn-clear").addEventListener("click", () => {
      this._clearQueue();
    });
  }

  // ---------------------------------------------------------------------------
  // Display update
  // ---------------------------------------------------------------------------

  _updateDisplay() {
    const q = this._queueState;
    const active = q?.active || null;
    const pending = q?.pending || [];
    const hasAnything = !!active || pending.length > 0;

    // --- Active command ---
    const activeSection = this.shadowRoot.getElementById("active-section");
    const activeName = this.shadowRoot.getElementById("active-name");
    const activeDetail = this.shadowRoot.getElementById("active-detail");
    const activeProgress = this.shadowRoot.getElementById("active-progress");
    const activeProgressFill = this.shadowRoot.getElementById("active-progress-fill");

    if (active) {
      activeSection.style.display = "";
      activeName.textContent = active.command || "Unknown";

      // Build detail line: phase + status + elapsed
      const parts = [];
      if (active.status) parts.push(active.status);
      if (active.elapsed != null) parts.push(`${active.elapsed.toFixed(1)}s`);
      activeDetail.textContent = parts.join(" \u2022 "); // bullet separator

      // Progress bar — only show if the entry has a numeric progress field
      if (active.progress != null && isFinite(active.progress)) {
        activeProgress.style.display = "";
        const pct = Math.min(100, Math.max(0, active.progress * 100));
        activeProgressFill.style.width = `${pct}%`;
      } else {
        activeProgress.style.display = "none";
      }
    } else {
      activeSection.style.display = "none";
    }

    // --- Queue count ---
    const queueCountEl = this.shadowRoot.getElementById("queue-count");
    const countNumber = this.shadowRoot.getElementById("count-number");

    if (pending.length > 0) {
      queueCountEl.style.display = "";
      countNumber.textContent = String(pending.length);
    } else {
      queueCountEl.style.display = "none";
    }

    // --- Pending list ---
    const listEl = this.shadowRoot.getElementById("queue-list");
    listEl.innerHTML = "";

    for (let i = 0; i < pending.length; i++) {
      const entry = pending[i];
      const item = document.createElement("div");
      item.className = "queue-item";

      const idx = document.createElement("span");
      idx.className = "queue-index";
      idx.textContent = String(i + 1);

      const name = document.createElement("span");
      name.className = "queue-item-name";
      name.textContent = entry.command || "Unknown";

      item.appendChild(idx);
      item.appendChild(name);

      // Params summary — show a compact representation if params exist
      if (entry.params && Object.keys(entry.params).length > 0) {
        const params = document.createElement("span");
        params.className = "queue-item-params";
        params.textContent = this._summarizeParams(entry.params);
        params.title = JSON.stringify(entry.params);
        item.appendChild(params);
      }

      listEl.appendChild(item);
    }

    // --- Empty state ---
    const emptyState = this.shadowRoot.getElementById("empty-state");
    emptyState.style.display = hasAnything ? "none" : "";

    // --- Button enable/disable ---
    const btnInterrupt = this.shadowRoot.getElementById("btn-interrupt");
    const btnClear = this.shadowRoot.getElementById("btn-clear");
    btnInterrupt.disabled = !hasAnything;
    btnClear.disabled = pending.length === 0 && !active;
  }

  /**
   * Produce a short human-readable summary of command params.
   * e.g. { heading: 45, throttle: 0.8 } -> "heading:45 throttle:0.8"
   */
  _summarizeParams(params) {
    if (!params || typeof params !== "object") return "";
    const entries = Object.entries(params);
    if (entries.length === 0) return "";
    return entries
      .slice(0, 3) // limit to 3 fields
      .map(([k, v]) => {
        const val = typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(1)) : String(v);
        return `${k}:${val}`;
      })
      .join(" ");
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("helm-queue-panel", HelmQueuePanel);
export { HelmQueuePanel };
