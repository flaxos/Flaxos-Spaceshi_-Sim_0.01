/**
 * Event Log Component
 * Scrolling log with timestamp prefix, category tags, and color coding
 */

import { wsClient } from "../js/ws-client.js";

const CATEGORY_COLORS = {
  NAV: "#00aaff",  // Navigation - cyan
  SEN: "#00ff88",  // Sensors - green
  WPN: "#ff4444",  // Weapons - red
  SYS: "#ffaa00",  // System - amber
  COM: "#aa88ff",  // Comms - purple
  ERR: "#ff4444",  // Error - red
  CMD: "#888899",  // Command - gray
  RSP: "#00ff88",  // Response - green
};

const MAX_ENTRIES = 500;

class EventLog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._autoScroll = true;
    this._paused = false;
  }

  connectedCallback() {
    this.render();
    this._bindEvents();
  }

  disconnectedCallback() {
    this._unbindEvents();
  }

  _bindEvents() {
    // Listen for server events
    this._onResponse = (e) => this._handleResponse(e.detail);
    this._onEvent = (e) => this._handleEvent(e.detail);
    this._onError = (e) => this._addEntry("ERR", e.detail.error || "Server error");
    this._onStatusChange = (e) => this._addEntry("SYS", `Connection: ${e.detail.status}`);

    wsClient.addEventListener("response", this._onResponse);
    wsClient.addEventListener("event", this._onEvent);
    wsClient.addEventListener("server_error", this._onError);
    wsClient.addEventListener("status_change", this._onStatusChange);
  }

  _unbindEvents() {
    wsClient.removeEventListener("response", this._onResponse);
    wsClient.removeEventListener("event", this._onEvent);
    wsClient.removeEventListener("server_error", this._onError);
    wsClient.removeEventListener("status_change", this._onStatusChange);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 100%;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
        }

        .controls {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px;
          border-bottom: 1px solid var(--border-default, #2a2a3a);
          background: rgba(0, 0, 0, 0.2);
        }

        .control-btn {
          background: transparent;
          border: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-secondary, #888899);
          padding: 4px 8px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.7rem;
          min-height: auto;
        }

        .control-btn:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary, #e0e0e0);
        }

        .control-btn.active {
          background: var(--status-info, #00aaff);
          color: #000;
          border-color: var(--status-info, #00aaff);
        }

        .scroll-indicator {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          margin-left: auto;
        }

        .scroll-indicator.paused {
          color: var(--status-warning, #ffaa00);
        }

        .log-container {
          flex: 1;
          overflow-y: auto;
          padding: 8px;
        }

        .log-entry {
          display: flex;
          gap: 8px;
          padding: 4px 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.03);
          line-height: 1.4;
        }

        .log-entry:last-child {
          border-bottom: none;
        }

        .timestamp {
          color: var(--text-dim, #555566);
          white-space: nowrap;
          flex-shrink: 0;
        }

        .category {
          font-weight: 600;
          white-space: nowrap;
          flex-shrink: 0;
          min-width: 40px;
        }

        .message {
          color: var(--text-primary, #e0e0e0);
          word-break: break-word;
          flex: 1;
        }

        .empty-state {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: var(--text-dim, #555566);
          font-style: italic;
        }
      </style>

      <div class="controls">
        <button class="control-btn" id="clear-btn">Clear</button>
        <button class="control-btn" id="autoscroll-btn" title="Auto-scroll">▼ Auto</button>
        <span class="scroll-indicator" id="scroll-indicator">▼ Auto-scroll</span>
      </div>
      <div class="log-container" id="log-container">
        <div class="empty-state">No events yet</div>
      </div>
    `;

    this._setupControls();
  }

  _setupControls() {
    const container = this.shadowRoot.getElementById("log-container");
    const clearBtn = this.shadowRoot.getElementById("clear-btn");
    const autoscrollBtn = this.shadowRoot.getElementById("autoscroll-btn");
    const indicator = this.shadowRoot.getElementById("scroll-indicator");

    clearBtn.addEventListener("click", () => this.clear());

    autoscrollBtn.addEventListener("click", () => {
      this._autoScroll = !this._autoScroll;
      this._updateScrollIndicator();
      if (this._autoScroll) {
        this._scrollToBottom();
      }
    });

    // Pause auto-scroll when user scrolls up
    container.addEventListener("scroll", () => {
      const isAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;
      if (!isAtBottom && this._autoScroll) {
        this._paused = true;
        this._updateScrollIndicator();
      } else if (isAtBottom) {
        this._paused = false;
        this._updateScrollIndicator();
      }
    });

    // Click to resume auto-scroll
    indicator.addEventListener("click", () => {
      this._paused = false;
      this._autoScroll = true;
      this._scrollToBottom();
      this._updateScrollIndicator();
    });
  }

  _updateScrollIndicator() {
    const indicator = this.shadowRoot.getElementById("scroll-indicator");
    const btn = this.shadowRoot.getElementById("autoscroll-btn");

    if (this._paused) {
      indicator.textContent = "⏸ Paused (click to resume)";
      indicator.classList.add("paused");
    } else if (this._autoScroll) {
      indicator.textContent = "▼ Auto-scroll";
      indicator.classList.remove("paused");
    } else {
      indicator.textContent = "Manual scroll";
      indicator.classList.remove("paused");
    }

    btn.classList.toggle("active", this._autoScroll && !this._paused);
  }

  _scrollToBottom() {
    const container = this.shadowRoot.getElementById("log-container");
    container.scrollTop = container.scrollHeight;
  }

  /**
   * Add an entry to the log
   * @param {string} category - Category tag (NAV, SEN, WPN, SYS, COM, ERR, CMD, RSP)
   * @param {string} message - Log message
   */
  addEntry(category, message) {
    this._addEntry(category, message);
  }

  _addEntry(category, message) {
    const timestamp = new Date().toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });

    const entry = { timestamp, category, message };
    this._entries.push(entry);

    // Limit entries
    while (this._entries.length > MAX_ENTRIES) {
      this._entries.shift();
    }

    this._renderEntry(entry);

    // Auto-scroll if enabled and not paused
    if (this._autoScroll && !this._paused) {
      this._scrollToBottom();
    }

    // Resume on critical events
    if (category === "ERR" && this._paused) {
      this._paused = false;
      this._scrollToBottom();
      this._updateScrollIndicator();
    }
  }

  _renderEntry(entry) {
    const container = this.shadowRoot.getElementById("log-container");

    // Remove empty state if present
    const emptyState = container.querySelector(".empty-state");
    if (emptyState) {
      emptyState.remove();
    }

    const el = document.createElement("div");
    el.className = "log-entry";

    const color = CATEGORY_COLORS[entry.category] || "#888899";

    el.innerHTML = `
      <span class="timestamp">${entry.timestamp}</span>
      <span class="category" style="color: ${color}">[${entry.category}]</span>
      <span class="message">${this._escapeHtml(entry.message)}</span>
    `;

    container.appendChild(el);

    // Remove old entries from DOM
    while (container.children.length > MAX_ENTRIES) {
      container.firstChild.remove();
    }
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Handle server response
   */
  _handleResponse(data) {
    // Determine category based on response content
    let category = "RSP";
    let message = "";

    if (data.ok === false) {
      category = "ERR";
      message = data.error || "Request failed";
    } else if (data.ships || data.state) {
      category = "SYS";
      message = `State update received`;
    } else if (data.contacts) {
      category = "SEN";
      message = `${data.contacts?.length || 0} contacts`;
    } else if (data.mission) {
      category = "SYS";
      message = `Mission: ${data.mission?.status || "unknown"}`;
    } else {
      message = JSON.stringify(data).slice(0, 100);
    }

    this._addEntry(category, message);
  }

  /**
   * Handle server events
   */
  _handleEvent(data) {
    const eventType = data.type || data.event || "unknown";
    let category = "SYS";
    let message = data.message || eventType;

    // Categorize by event type
    if (eventType.includes("nav") || eventType.includes("autopilot") || eventType.includes("thrust")) {
      category = "NAV";
    } else if (eventType.includes("sensor") || eventType.includes("contact") || eventType.includes("ping")) {
      category = "SEN";
    } else if (eventType.includes("weapon") || eventType.includes("fire") || eventType.includes("pdc") || eventType.includes("torpedo")) {
      category = "WPN";
    } else if (eventType.includes("comm") || eventType.includes("hail") || eventType.includes("fleet")) {
      category = "COM";
    } else if (eventType.includes("error") || eventType.includes("warning") || eventType.includes("critical")) {
      category = "ERR";
    }

    this._addEntry(category, message);
  }

  /**
   * Clear the log
   */
  clear() {
    this._entries = [];
    const container = this.shadowRoot.getElementById("log-container");
    container.innerHTML = '<div class="empty-state">No events yet</div>';
  }

  /**
   * Log a command being sent
   */
  logCommand(cmd, args = {}) {
    const argsStr = Object.keys(args).length > 0 ? ` ${JSON.stringify(args)}` : "";
    this._addEntry("CMD", `>> ${cmd}${argsStr}`);
  }
}

customElements.define("event-log", EventLog);
export { EventLog };
