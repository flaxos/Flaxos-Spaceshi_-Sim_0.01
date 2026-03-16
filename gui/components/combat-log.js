/**
 * Combat Log Component
 * Persistent log of combat events with full causal chains.
 * Filterable by event type, weapon, and target.
 *
 * Each entry shows a narrative: cause -> effect -> outcome.
 * This is the primary tool for player learning.
 */

import { wsClient } from "../js/ws-client.js";

const SEVERITY_COLORS = {
  hit: "#00ff88",      // Green - confirmed hit
  miss: "#888899",     // Gray - miss
  damage: "#ffaa00",   // Amber - damage dealt/received
  critical: "#ff4444", // Red - critical (cascade, destroyed)
  info: "#00aaff",     // Cyan - informational (lock, reload)
};

const EVENT_TYPE_LABELS = {
  hit: "HIT",
  miss: "MISS",
  damage: "DMG",
  cascade: "CASCADE",
  cascade_cleared: "CLEAR",
  reload: "RELOAD",
  lock: "LOCK",
  lock_lost: "LOST",
};

const POLL_INTERVAL_MS = 800;

class CombatLog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._latestId = 0;
    this._autoScroll = true;
    this._paused = false;
    this._pollTimer = null;
    this._filter = "all"; // all, hit, miss, damage, cascade, reload, lock
    this._weaponFilter = "all";
    this._targetFilter = "all";
    this._expandedEntries = new Set();
  }

  connectedCallback() {
    this.render();
    this._startPolling();
  }

  disconnectedCallback() {
    this._stopPolling();
  }

  _startPolling() {
    this._stopPolling();
    this._poll();
    this._pollTimer = setInterval(() => this._poll(), POLL_INTERVAL_MS);
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  async _poll() {
    try {
      const params = { since_id: this._latestId, limit: 50 };
      if (this._filter !== "all") {
        params.event_type = this._filter;
      }
      if (this._weaponFilter !== "all") {
        params.weapon = this._weaponFilter;
      }
      if (this._targetFilter !== "all") {
        params.target = this._targetFilter;
      }

      const response = await wsClient.send("get_combat_log", params);

      if (response && response.ok !== false && Array.isArray(response.entries)) {
        if (response.entries.length > 0) {
          for (const entry of response.entries) {
            this._entries.push(entry);
          }

          // Cap stored entries
          while (this._entries.length > 500) {
            this._entries.shift();
          }

          this._latestId = response.latest_id || this._latestId;
          this._renderNewEntries(response.entries);
        }
      }
    } catch {
      // Ignore polling errors
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.78rem;
        }

        .toolbar {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 8px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          background: rgba(0, 0, 0, 0.2);
          flex-wrap: wrap;
        }

        .filter-btn {
          background: transparent;
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-secondary, #888899);
          padding: 3px 8px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.68rem;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          min-height: auto;
          transition: all 0.1s ease;
        }

        .filter-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary, #e0e0e0);
        }

        .filter-btn.active {
          background: var(--status-info, #00aaff);
          color: #000;
          border-color: var(--status-info, #00aaff);
        }

        .filter-btn.hit.active {
          background: #00ff88;
        }

        .filter-btn.miss.active {
          background: #888899;
          color: #000;
        }

        .filter-btn.damage.active {
          background: #ffaa00;
          color: #000;
        }

        .filter-btn.critical.active {
          background: #ff4444;
        }

        .spacer { flex: 1; }

        .scroll-indicator {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          cursor: pointer;
        }

        .scroll-indicator.paused {
          color: var(--status-warning, #ffaa00);
        }

        .log-container {
          flex: 1;
          overflow-y: auto;
          padding: 4px 8px;
          min-height: 80px;
        }

        .log-entry {
          padding: 6px 8px;
          margin-bottom: 4px;
          border-radius: 4px;
          background: rgba(0, 0, 0, 0.15);
          border-left: 3px solid var(--text-dim, #555566);
          cursor: pointer;
          transition: background 0.1s ease;
        }

        .log-entry:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .log-entry.severity-hit {
          border-left-color: #00ff88;
        }

        .log-entry.severity-miss {
          border-left-color: #555566;
        }

        .log-entry.severity-damage {
          border-left-color: #ffaa00;
        }

        .log-entry.severity-critical {
          border-left-color: #ff4444;
        }

        .log-entry.severity-info {
          border-left-color: #00aaff;
        }

        .entry-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .entry-time {
          color: var(--text-dim, #555566);
          font-size: 0.68rem;
          flex-shrink: 0;
        }

        .entry-tag {
          font-weight: 600;
          font-size: 0.68rem;
          padding: 1px 5px;
          border-radius: 3px;
          flex-shrink: 0;
        }

        .entry-tag.hit { background: rgba(0, 255, 136, 0.15); color: #00ff88; }
        .entry-tag.miss { background: rgba(136, 136, 153, 0.15); color: #888899; }
        .entry-tag.damage { background: rgba(255, 170, 0, 0.15); color: #ffaa00; }
        .entry-tag.critical { background: rgba(255, 68, 68, 0.15); color: #ff4444; }
        .entry-tag.info { background: rgba(0, 170, 255, 0.15); color: #00aaff; }

        .entry-summary {
          color: var(--text-primary, #e0e0e0);
          font-size: 0.75rem;
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .entry-expand {
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          flex-shrink: 0;
        }

        .causal-chain {
          display: none;
          margin-top: 6px;
          padding: 6px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 3px;
        }

        .log-entry.expanded .causal-chain {
          display: block;
        }

        .chain-step {
          display: flex;
          align-items: flex-start;
          gap: 6px;
          padding: 2px 0;
          color: var(--text-secondary, #888899);
          font-size: 0.72rem;
          line-height: 1.4;
        }

        .chain-arrow {
          color: var(--text-dim, #555566);
          flex-shrink: 0;
          margin-top: 1px;
        }

        .chain-step:first-child .chain-arrow {
          visibility: hidden;
        }

        .empty-state {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: var(--text-dim, #555566);
          font-family: var(--font-sans, "Inter", sans-serif);
          font-style: italic;
          font-size: 0.85rem;
        }

        .count-badge {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          margin-left: auto;
          padding-right: 4px;
        }
      </style>

      <div class="toolbar">
        <button class="filter-btn active" data-filter="all">ALL</button>
        <button class="filter-btn hit" data-filter="hit">HIT</button>
        <button class="filter-btn miss" data-filter="miss">MISS</button>
        <button class="filter-btn damage" data-filter="damage">DMG</button>
        <button class="filter-btn critical" data-filter="cascade">CASCADE</button>
        <button class="filter-btn" data-filter="reload">RELOAD</button>
        <button class="filter-btn" data-filter="lock">LOCK</button>
        <span class="spacer"></span>
        <span class="count-badge" id="count-badge">0 entries</span>
        <span class="scroll-indicator" id="scroll-indicator">&#x25BC; Auto</span>
      </div>
      <div class="log-container" id="log-container">
        <div class="empty-state">No combat events yet</div>
      </div>
    `;

    this._setupControls();
  }

  _setupControls() {
    // Filter buttons
    const filterBtns = this.shadowRoot.querySelectorAll(".filter-btn");
    filterBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const filter = btn.dataset.filter;
        this._filter = filter;

        // Update active state
        filterBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        // Reset and re-render with new filter
        this._latestId = 0;
        this._entries = [];
        const container = this.shadowRoot.getElementById("log-container");
        container.innerHTML = '<div class="empty-state">Loading...</div>';

        // Immediate poll with new filter
        this._poll();
      });
    });

    // Scroll handling
    const container = this.shadowRoot.getElementById("log-container");
    const indicator = this.shadowRoot.getElementById("scroll-indicator");

    container.addEventListener("scroll", () => {
      const atBottom =
        container.scrollTop + container.clientHeight >=
        container.scrollHeight - 20;
      if (!atBottom && this._autoScroll) {
        this._paused = true;
        this._updateScrollIndicator();
      } else if (atBottom) {
        this._paused = false;
        this._updateScrollIndicator();
      }
    });

    indicator.addEventListener("click", () => {
      this._paused = false;
      this._autoScroll = true;
      this._scrollToBottom();
      this._updateScrollIndicator();
    });
  }

  _updateScrollIndicator() {
    const indicator = this.shadowRoot.getElementById("scroll-indicator");
    if (this._paused) {
      indicator.textContent = "\u23F8 Paused";
      indicator.classList.add("paused");
    } else {
      indicator.textContent = "\u25BC Auto";
      indicator.classList.remove("paused");
    }
  }

  _scrollToBottom() {
    const container = this.shadowRoot.getElementById("log-container");
    container.scrollTop = container.scrollHeight;
  }

  _renderNewEntries(entries) {
    const container = this.shadowRoot.getElementById("log-container");

    // Remove empty state
    const empty = container.querySelector(".empty-state");
    if (empty) empty.remove();

    for (const entry of entries) {
      const el = this._createEntryElement(entry);
      container.appendChild(el);
    }

    // Cap DOM nodes
    while (container.children.length > 500) {
      container.firstChild.remove();
    }

    // Update count
    const badge = this.shadowRoot.getElementById("count-badge");
    badge.textContent = `${this._entries.length} entries`;

    // Auto-scroll
    if (this._autoScroll && !this._paused) {
      this._scrollToBottom();
    }
  }

  _createEntryElement(entry) {
    const el = document.createElement("div");
    el.className = `log-entry severity-${entry.severity || "info"}`;
    el.dataset.entryId = entry.id;

    const tagLabel =
      EVENT_TYPE_LABELS[entry.event_type] || entry.event_type?.toUpperCase() || "?";
    const tagClass = entry.severity || "info";

    const simTime = entry.sim_time != null ? `T+${entry.sim_time.toFixed(1)}s` : "";

    // Build chain steps HTML
    const chainHtml = (entry.chain || [])
      .map(
        (step, i) => `
        <div class="chain-step">
          <span class="chain-arrow">${i === 0 ? "\u2022" : "\u2192"}</span>
          <span>${this._escapeHtml(step)}</span>
        </div>
      `
      )
      .join("");

    el.innerHTML = `
      <div class="entry-header">
        <span class="entry-time">${simTime}</span>
        <span class="entry-tag ${tagClass}">${tagLabel}</span>
        <span class="entry-summary">${this._escapeHtml(entry.summary || "")}</span>
        <span class="entry-expand">${entry.chain?.length > 0 ? "\u25B6" : ""}</span>
      </div>
      ${
        chainHtml
          ? `<div class="causal-chain">${chainHtml}</div>`
          : ""
      }
    `;

    // Toggle expand on click
    if (entry.chain && entry.chain.length > 0) {
      el.addEventListener("click", () => {
        el.classList.toggle("expanded");
        const expandIcon = el.querySelector(".entry-expand");
        if (expandIcon) {
          expandIcon.textContent = el.classList.contains("expanded")
            ? "\u25BC"
            : "\u25B6";
        }
      });
    }

    return el;
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

customElements.define("combat-log", CombatLog);
export { CombatLog };
