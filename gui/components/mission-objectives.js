/**
 * Mission Objectives Display
 * Shows mission status, objectives, and time
 */

import { wsClient } from "../js/ws-client.js";

class MissionObjectives extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._mission = null;
    this._pollInterval = null;
    this._scenarioLoadedHandler = null;
  }

  connectedCallback() {
    this.render();
    this._startPolling();

    // Listen for scenario loads
    this._scenarioLoadedHandler = (e) => {
      if (e.detail.mission) {
        this._updateMission(e.detail.mission);
      } else {
        this._fetchMission();
      }
    };
    document.addEventListener("scenario-loaded", this._scenarioLoadedHandler);
  }

  disconnectedCallback() {
    this._stopPolling();
    if (this._scenarioLoadedHandler) {
      document.removeEventListener("scenario-loaded", this._scenarioLoadedHandler);
      this._scenarioLoadedHandler = null;
    }
  }

  _startPolling() {
    this._pollInterval = setInterval(() => {
      this._fetchMission();
    }, 2000);

    // Initial fetch
    this._fetchMission();
  }

  _stopPolling() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  async _fetchMission() {
    try {
      const response = await wsClient.send("get_mission", {});
      if (response && response.ok !== false) {
        this._updateMission(response.mission || response);
      }
    } catch (error) {
      // Ignore polling errors
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .no-mission {
          text-align: center;
          padding: 24px;
          color: var(--text-dim, #555566);
          font-style: italic;
        }

        .mission-header {
          margin-bottom: 16px;
        }

        .mission-name {
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 4px;
        }

        .mission-desc {
          font-size: 0.8rem;
          color: var(--text-secondary, #888899);
        }

        .status-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }

        .status-dot.in_progress {
          background: var(--status-info, #00aaff);
          box-shadow: 0 0 8px var(--status-info, #00aaff);
          animation: pulse 1.5s ease-in-out infinite;
        }

        .status-dot.success {
          background: var(--status-nominal, #00ff88);
          box-shadow: 0 0 8px var(--status-nominal, #00ff88);
        }

        .status-dot.failure {
          background: var(--status-critical, #ff4444);
          box-shadow: 0 0 8px var(--status-critical, #ff4444);
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        .status-text {
          font-size: 0.8rem;
          font-weight: 600;
          text-transform: uppercase;
        }

        .status-text.in_progress { color: var(--status-info, #00aaff); }
        .status-text.success { color: var(--status-nominal, #00ff88); }
        .status-text.failure { color: var(--status-critical, #ff4444); }

        .time-display {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
          color: var(--text-primary, #e0e0e0);
        }

        .objectives-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .objective {
          padding: 10px 12px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          border-left: 3px solid var(--border-default, #2a2a3a);
        }

        .objective.completed {
          border-left-color: var(--status-nominal, #00ff88);
          opacity: 0.7;
        }

        .objective.failed {
          border-left-color: var(--status-critical, #ff4444);
          opacity: 0.7;
        }

        .objective.required {
          border-left-color: var(--status-info, #00aaff);
        }

        .objective-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .objective-check {
          font-size: 0.9rem;
        }

        .objective-check.completed { color: var(--status-nominal, #00ff88); }
        .objective-check.failed { color: var(--status-critical, #ff4444); }
        .objective-check.pending { color: var(--text-dim, #555566); }

        .objective-text {
          flex: 1;
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
        }

        .objective.completed .objective-text {
          text-decoration: line-through;
        }

        .objective-meta {
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          margin-top: 4px;
        }

        .optional-tag {
          font-size: 0.65rem;
          padding: 2px 6px;
          background: rgba(255, 170, 0, 0.2);
          color: var(--status-warning, #ffaa00);
          border-radius: 3px;
        }

        .hints-section {
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .hints-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        .hint {
          padding: 8px 12px;
          background: rgba(255, 170, 0, 0.1);
          border-left: 3px solid var(--status-warning, #ffaa00);
          border-radius: 0 6px 6px 0;
          font-size: 0.8rem;
          color: var(--text-primary, #e0e0e0);
          margin-bottom: 6px;
        }

        .result-message {
          margin-top: 16px;
          padding: 16px;
          border-radius: 8px;
          text-align: center;
        }

        .result-message.success {
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
        }

        .result-message.failure {
          background: rgba(255, 68, 68, 0.1);
          border: 1px solid var(--status-critical, #ff4444);
          color: var(--status-critical, #ff4444);
        }

        .result-title {
          font-size: 1.1rem;
          font-weight: 600;
          margin-bottom: 8px;
        }

        .result-text {
          font-size: 0.85rem;
        }
      </style>

      <div id="content">
        <div class="no-mission">No mission loaded</div>
      </div>
    `;
  }

  _updateMission(mission) {
    this._mission = mission;
    this._renderMission();
  }

  _renderMission() {
    const content = this.shadowRoot.getElementById("content");

    if (!this._mission || this._mission.available === false) {
      content.innerHTML = '<div class="no-mission">No mission loaded</div>';
      return;
    }

    const status = this._mission.mission_status || this._mission.status || "in_progress";
    const objectives = this._getObjectives();
    const timeDisplay = this._formatTime();
    const hints = this._mission.hints || [];

    content.innerHTML = `
      <div class="mission-header">
        <div class="mission-name">${this._mission.name || "Mission"}</div>
        <div class="mission-desc">${this._mission.description || this._mission.briefing || ""}</div>
      </div>

      <div class="status-bar">
        <div class="status-indicator">
          <span class="status-dot ${status}"></span>
          <span class="status-text ${status}">${status.replace("_", " ")}</span>
        </div>
        <div class="time-display">${timeDisplay}</div>
      </div>

      <div class="objectives-list">
        ${objectives.map(obj => this._renderObjective(obj)).join("")}
      </div>

      ${hints.length > 0 ? `
        <div class="hints-section">
          <div class="hints-title">Hints</div>
          ${hints.map(hint => `
            <div class="hint">${hint.message || hint}</div>
          `).join("")}
        </div>
      ` : ""}

      ${status === "success" ? `
        <div class="result-message success">
          <div class="result-title">✓ MISSION COMPLETE</div>
          <div class="result-text">${this._mission.success_message || "All objectives achieved."}</div>
        </div>
      ` : ""}

      ${status === "failure" ? `
        <div class="result-message failure">
          <div class="result-title">✕ MISSION FAILED</div>
          <div class="result-text">${this._mission.failure_message || "Mission objectives not met."}</div>
        </div>
      ` : ""}
    `;
  }

  _getObjectives() {
    const objectives = this._mission.objectives || {};

    if (Array.isArray(objectives)) {
      return objectives;
    }

    return Object.entries(objectives).map(([id, obj]) => ({
      id,
      ...obj
    }));
  }

  _renderObjective(obj) {
    const status = obj.status || "pending";
    const isRequired = obj.required !== false;
    const checkIcon = status === "completed" ? "☑" : status === "failed" ? "☒" : "☐";

    const classes = [
      "objective",
      status,
      isRequired ? "required" : ""
    ].filter(Boolean).join(" ");

    return `
      <div class="${classes}">
        <div class="objective-header">
          <span class="objective-check ${status}">${checkIcon}</span>
          <span class="objective-text">${obj.description || obj.id}</span>
          ${!isRequired ? '<span class="optional-tag">Optional</span>' : ""}
        </div>
        ${obj.type || obj.progress ? `
          <div class="objective-meta">
            ${obj.type ? `Type: ${obj.type}` : ""}
            ${obj.progress ? ` • Progress: ${obj.progress}` : ""}
          </div>
        ` : ""}
      </div>
    `;
  }

  _formatTime() {
    const timeRemaining = this._mission.time_remaining;
    const timeElapsed = this._mission.time_elapsed;
    const timeLimit = this._mission.time_limit;

    if (typeof timeRemaining === "number" && timeRemaining > 0) {
      const mins = Math.floor(timeRemaining / 60);
      const secs = Math.floor(timeRemaining % 60);
      return `${mins}:${secs.toString().padStart(2, "0")} remaining`;
    }

    if (typeof timeElapsed === "number" && typeof timeLimit === "number") {
      const elapsed = this._formatSeconds(timeElapsed);
      const limit = this._formatSeconds(timeLimit);
      return `${elapsed} / ${limit}`;
    }

    if (typeof timeElapsed === "number") {
      return this._formatSeconds(timeElapsed);
    }

    return "--:--";
  }

  _formatSeconds(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  /**
   * Get current mission data
   */
  getMission() {
    return this._mission;
  }
}

customElements.define("mission-objectives", MissionObjectives);
export { MissionObjectives };
