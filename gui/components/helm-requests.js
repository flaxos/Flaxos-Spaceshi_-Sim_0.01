/**
 * Helm Requests Panel
 * Displays pending maneuver requests from other bridge stations
 * for the helm officer to review and execute.
 */

import { helmRequests } from "../js/helm-requests.js";
import { wsClient } from "../js/ws-client.js";

class HelmRequestsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._boundUpdate = this._updateDisplay.bind(this);
  }

  connectedCallback() {
    this.render();
    this._setupEvents();
    this._updateDisplay();
  }

  disconnectedCallback() {
    window.removeEventListener("helm:request_created", this._boundUpdate);
    window.removeEventListener("helm:request_executed", this._boundUpdate);
    window.removeEventListener("helm:request_dismissed", this._boundUpdate);
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 16px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
        }

        .badge {
          background: var(--status-warning, #ffaa00);
          color: var(--bg-primary, #0a0a0f);
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.7rem;
          font-weight: 600;
        }

        .badge.empty {
          background: var(--text-dim, #555566);
        }

        .requests-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 300px;
          overflow-y: auto;
        }

        .request-card {
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          padding: 12px;
          transition: all 0.15s ease;
        }

        .request-card:hover {
          border-color: var(--status-info, #00aaff);
        }

        .request-card.point_at {
          border-left: 3px solid var(--status-info, #00aaff);
        }

        .request-card.intercept {
          border-left: 3px solid var(--status-warning, #ffaa00);
        }

        .request-card.match_velocity {
          border-left: 3px solid var(--status-nominal, #00ff88);
        }

        .request-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 8px;
        }

        .request-type {
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          font-size: 0.75rem;
        }

        .request-meta {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-align: right;
        }

        .request-source {
          color: var(--status-info, #00aaff);
        }

        .request-params {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          padding: 8px;
          margin-bottom: 8px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.8rem;
        }

        .param-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
        }

        .param-row:last-child {
          margin-bottom: 0;
        }

        .param-label {
          color: var(--text-dim, #555566);
        }

        .param-value {
          color: var(--text-primary, #e0e0e0);
        }

        .param-value.highlight {
          color: var(--status-info, #00aaff);
          font-weight: 600;
        }

        .request-actions {
          display: flex;
          gap: 8px;
        }

        .action-btn {
          flex: 1;
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 36px;
          transition: all 0.1s ease;
        }

        .execute-btn {
          background: var(--status-nominal, #00ff88);
          border: none;
          color: var(--bg-primary, #0a0a0f);
        }

        .execute-btn:hover {
          filter: brightness(1.1);
        }

        .dismiss-btn {
          background: transparent;
          border: 1px solid var(--text-dim, #555566);
          color: var(--text-dim, #555566);
        }

        .dismiss-btn:hover {
          border-color: var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .empty-state {
          text-align: center;
          padding: 24px;
          color: var(--text-dim, #555566);
        }

        .empty-icon {
          font-size: 2rem;
          margin-bottom: 8px;
          opacity: 0.5;
        }

        .empty-text {
          font-size: 0.85rem;
          margin-bottom: 4px;
        }

        .empty-hint {
          font-size: 0.7rem;
          font-style: italic;
        }

        .history-section {
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .history-title {
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
          text-transform: uppercase;
          margin-bottom: 8px;
        }

        .history-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          margin-bottom: 4px;
          font-size: 0.7rem;
        }

        .history-item.executed {
          border-left: 2px solid var(--status-nominal, #00ff88);
        }

        .history-item.dismissed {
          border-left: 2px solid var(--text-dim, #555566);
          opacity: 0.6;
        }

        .history-text {
          color: var(--text-secondary, #888899);
        }

        .history-time {
          color: var(--text-dim, #555566);
          font-size: 0.65rem;
        }

        .notification-pulse {
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
      </style>

      <div class="header">
        <span class="title">Pending Requests</span>
        <span class="badge empty" id="badge">0</span>
      </div>

      <div class="requests-list" id="requests-list">
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <div class="empty-text">No pending requests</div>
          <div class="empty-hint">Requests from other stations will appear here</div>
        </div>
      </div>

      <div class="history-section" id="history-section" style="display: none;">
        <div class="history-title">Recent History</div>
        <div id="history-list"></div>
      </div>
    `;
  }

  _setupEvents() {
    // Listen for new requests
    window.addEventListener("helm:request_created", this._boundUpdate);
    window.addEventListener("helm:request_executed", this._boundUpdate);
    window.addEventListener("helm:request_dismissed", this._boundUpdate);

    // Handle clicks on request actions
    this.shadowRoot.getElementById("requests-list").addEventListener("click", (e) => {
      const btn = e.target.closest(".action-btn");
      if (!btn) return;

      const requestId = parseInt(btn.dataset.requestId, 10);
      if (btn.classList.contains("execute-btn")) {
        this._executeRequest(requestId);
      } else if (btn.classList.contains("dismiss-btn")) {
        this._dismissRequest(requestId);
      }
    });
  }

  async _executeRequest(requestId) {
    const request = helmRequests.getAllRequests().find(r => r.id === requestId);
    if (!request || request.status !== 'pending') return;

    try {
      // Execute based on request type
      if (request.type === 'point_at' || request.type === 'set_heading') {
        await wsClient.sendShipCommand("set_orientation", {
          pitch: request.params.pitch || 0,
          yaw: request.params.yaw || 0,
          roll: request.params.roll || 0
        });
      } else if (request.type === 'intercept') {
        // Could trigger autopilot intercept mode
        await wsClient.sendShipCommand("set_autopilot", {
          mode: "intercept",
          target: request.targetId
        });
      } else if (request.type === 'match_velocity') {
        await wsClient.sendShipCommand("set_autopilot", {
          mode: "match",
          target: request.targetId
        });
      }

      // Mark as executed
      helmRequests.executeRequest(requestId);
      this._showMessage(`Executed: ${request.description}`, "success");
    } catch (error) {
      console.error("Failed to execute request:", error);
      this._showMessage(`Failed: ${error.message}`, "error");
    }
  }

  _dismissRequest(requestId) {
    const request = helmRequests.dismissRequest(requestId);
    if (request) {
      this._showMessage(`Dismissed: ${request.description}`, "info");
    }
  }

  _updateDisplay() {
    const pending = helmRequests.getPendingRequests();
    const all = helmRequests.getAllRequests();
    const history = all.filter(r => r.status !== 'pending').slice(-5).reverse();

    // Update badge
    const badge = this.shadowRoot.getElementById("badge");
    badge.textContent = pending.length;
    badge.classList.toggle("empty", pending.length === 0);
    badge.classList.toggle("notification-pulse", pending.length > 0);

    // Update requests list
    const listEl = this.shadowRoot.getElementById("requests-list");
    if (pending.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <div class="empty-text">No pending requests</div>
          <div class="empty-hint">Requests from other stations will appear here</div>
        </div>
      `;
    } else {
      listEl.innerHTML = pending.map(req => this._renderRequest(req)).join("");
    }

    // Update history
    const historySection = this.shadowRoot.getElementById("history-section");
    const historyList = this.shadowRoot.getElementById("history-list");
    if (history.length > 0) {
      historySection.style.display = "";
      historyList.innerHTML = history.map(req => this._renderHistoryItem(req)).join("");
    } else {
      historySection.style.display = "none";
    }
  }

  _renderRequest(request) {
    const age = this._formatAge(request.timestamp);
    const params = request.params || {};

    let paramsHtml = '';
    if (request.type === 'point_at' || request.type === 'set_heading') {
      paramsHtml = `
        <div class="param-row">
          <span class="param-label">Pitch:</span>
          <span class="param-value highlight">${(params.pitch || 0).toFixed(1)}°</span>
        </div>
        <div class="param-row">
          <span class="param-label">Yaw:</span>
          <span class="param-value highlight">${(params.yaw || 0).toFixed(1)}°</span>
        </div>
        ${params.range ? `
        <div class="param-row">
          <span class="param-label">Range:</span>
          <span class="param-value">${this._formatRange(params.range)}</span>
        </div>
        ` : ''}
      `;
    }

    return `
      <div class="request-card ${request.type}">
        <div class="request-header">
          <span class="request-type">${this._formatType(request.type)} ${request.targetId || ''}</span>
          <div class="request-meta">
            <div>From: <span class="request-source">${request.source}</span></div>
            <div>${age}</div>
          </div>
        </div>
        ${paramsHtml ? `<div class="request-params">${paramsHtml}</div>` : ''}
        <div class="request-actions">
          <button class="action-btn execute-btn" data-request-id="${request.id}">EXECUTE</button>
          <button class="action-btn dismiss-btn" data-request-id="${request.id}">DISMISS</button>
        </div>
      </div>
    `;
  }

  _renderHistoryItem(request) {
    const time = this._formatAge(request.executedAt || request.dismissedAt || request.timestamp);
    return `
      <div class="history-item ${request.status}">
        <span class="history-text">${request.status === 'executed' ? '✓' : '✗'} ${request.description}</span>
        <span class="history-time">${time}</span>
      </div>
    `;
  }

  _formatType(type) {
    const types = {
      'point_at': '◎ POINT AT',
      'intercept': '→ INTERCEPT',
      'match_velocity': '≈ MATCH VEL',
      'set_heading': '⟳ SET HEADING'
    };
    return types[type] || type.toUpperCase();
  }

  _formatAge(timestamp) {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 5) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ago`;
  }

  _formatRange(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(1)} km`;
    }
    return `${meters.toFixed(0)} m`;
  }

  _showMessage(text, type) {
    const systemMessages = document.getElementById("system-messages");
    if (systemMessages?.show) {
      systemMessages.show({ type, text });
    }
  }
}

customElements.define("helm-requests", HelmRequestsPanel);
export { HelmRequestsPanel };
