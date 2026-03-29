/**
 * Comms Choice Panel
 * Displays incoming mission dialogue choices from the branching system.
 * Polls get_comms_choices every 2s, presents choice options to the player,
 * and sends responses via comms_respond.
 *
 * Data flow:
 *   Server (BranchingMission) -> get_comms_choices -> this panel -> comms_respond -> server
 *
 * Choice lifecycle:
 *   1. Branch point activates, presents a CommsChoice
 *   2. Panel displays prompt + options with optional timeout countdown
 *   3. Player clicks an option -> comms_respond(choice_id, option_id)
 *   4. Choice moves from active to resolved
 */

import { wsClient } from "../js/ws-client.js";

class CommsChoicePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pollInterval = null;
    this._countdownInterval = null;
    this._choices = [];
    this._resolved = {};
    // Tracks the last choice we alerted on (avoid re-alerting)
    this._lastAlertedChoiceId = null;
    // Brief confirmation after choosing, cleared after 4s
    this._confirmationMsg = null;
    this._confirmationTimer = null;
  }

  connectedCallback() {
    this._render();
    this._startPolling();
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
    if (this._countdownInterval) {
      clearInterval(this._countdownInterval);
      this._countdownInterval = null;
    }
    if (this._confirmationTimer) {
      clearTimeout(this._confirmationTimer);
      this._confirmationTimer = null;
    }
  }

  _startPolling() {
    this._fetchChoices();
    this._pollInterval = setInterval(() => this._fetchChoices(), 2000);
    // Countdown ticks every 250ms for smooth timeout bars
    this._countdownInterval = setInterval(() => this._tickCountdowns(), 250);
  }

  async _fetchChoices() {
    try {
      const response = await wsClient.sendShipCommand("get_comms_choices", {});
      if (response && response.ok !== false) {
        const prev = this._choices;
        this._choices = response.choices || [];
        this._resolved = response.resolved || {};
        this._checkForNewChoices(prev, this._choices);
        this._updateDisplay();
      }
    } catch (err) {
      // Polling errors are expected when disconnected
    }
  }

  /**
   * Detect newly arrived choices and trigger visual alert.
   * Compares previous active set with current to find new entries.
   */
  _checkForNewChoices(prev, current) {
    const prevIds = new Set(prev.map(c => c.choice_id));
    for (const choice of current) {
      if (!prevIds.has(choice.choice_id) && choice.choice_id !== this._lastAlertedChoiceId) {
        this._lastAlertedChoiceId = choice.choice_id;
        this._triggerAlert();
      }
    }
  }

  /**
   * Visual pulse on the host element when a new choice arrives.
   * CSS animation handles the glow effect.
   */
  _triggerAlert() {
    const container = this.shadowRoot.getElementById("choices-container");
    if (container) {
      container.classList.remove("alert-pulse");
      // Force reflow to restart animation
      void container.offsetWidth;
      container.classList.add("alert-pulse");
    }
  }

  /**
   * Tick timeout countdowns and re-render progress bars.
   * Only updates the countdown elements, not the full display.
   */
  _tickCountdowns() {
    const now = Date.now() / 1000;
    for (const choice of this._choices) {
      if (choice.timeout == null || choice.presented_at == null) continue;
      const elapsed = now - choice.presented_at;
      const remaining = Math.max(0, choice.timeout - elapsed);
      const pct = Math.max(0, Math.min(100, (remaining / choice.timeout) * 100));

      const bar = this.shadowRoot.getElementById(`timeout-bar-${choice.choice_id}`);
      if (bar) {
        bar.style.width = `${pct}%`;
        // Color shift: green -> yellow -> red
        if (pct > 50) {
          bar.style.background = "var(--status-nominal, #00ff88)";
        } else if (pct > 20) {
          bar.style.background = "var(--status-warning, #ffaa00)";
        } else {
          bar.style.background = "var(--status-critical, #ff4444)";
        }
      }

      const label = this.shadowRoot.getElementById(`timeout-label-${choice.choice_id}`);
      if (label) {
        label.textContent = remaining > 0 ? `${Math.ceil(remaining)}s` : "EXPIRED";
      }
    }
  }

  async _respond(choiceId, optionId, optionLabel) {
    try {
      await wsClient.sendShipCommand("comms_respond", {
        choice_id: choiceId,
        option_id: optionId,
      });
      // Show brief confirmation
      this._confirmationMsg = `Responded: "${optionLabel}"`;
      this._updateDisplay();
      // Clear confirmation after 4s
      if (this._confirmationTimer) clearTimeout(this._confirmationTimer);
      this._confirmationTimer = setTimeout(() => {
        this._confirmationMsg = null;
        this._updateDisplay();
        this._confirmationTimer = null;
      }, 4000);
      // Immediately re-fetch to update state
      this._fetchChoices();
    } catch (err) {
      // Show error briefly
      this._confirmationMsg = "Failed to send response";
      this._updateDisplay();
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 12px;
        }

        .no-choices {
          text-align: center;
          padding: 20px 10px;
          color: var(--text-dim, #555566);
          font-style: italic;
          font-size: 0.75rem;
        }

        .choices-container {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        /* Alert pulse when new choice arrives */
        .choices-container.alert-pulse {
          animation: alert-glow 1.5s ease-out;
        }

        @keyframes alert-glow {
          0% { box-shadow: 0 0 20px rgba(0, 170, 255, 0.6); }
          100% { box-shadow: none; }
        }

        /* Individual choice card */
        .choice-card {
          background: rgba(0, 170, 255, 0.05);
          border: 1px solid rgba(0, 170, 255, 0.25);
          border-radius: 6px;
          overflow: hidden;
        }

        .choice-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px 6px;
        }

        .incoming-icon {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--status-info, #00aaff);
          animation: incoming-pulse 1.2s ease-in-out infinite;
          flex-shrink: 0;
        }

        @keyframes incoming-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--status-info, #00aaff); }
          50% { opacity: 0.3; box-shadow: none; }
        }

        .choice-contact {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--status-info, #00aaff);
        }

        .choice-prompt {
          padding: 6px 12px 12px;
          font-size: 0.8rem;
          line-height: 1.5;
          color: var(--text-primary, #e0e0e0);
          border-bottom: 1px solid rgba(42, 42, 58, 0.5);
        }

        /* Timeout bar */
        .timeout-section {
          padding: 6px 12px;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .timeout-track {
          flex: 1;
          height: 4px;
          background: rgba(42, 42, 58, 0.5);
          border-radius: 2px;
          overflow: hidden;
        }

        .timeout-fill {
          height: 100%;
          border-radius: 2px;
          background: var(--status-nominal, #00ff88);
          transition: width 0.25s linear;
        }

        .timeout-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
          min-width: 36px;
          text-align: right;
        }

        /* Options list */
        .options-list {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 8px;
        }

        .option-btn {
          display: flex;
          flex-direction: column;
          gap: 2px;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 4px;
          padding: 10px 12px;
          cursor: pointer;
          transition: all 0.15s ease;
          text-align: left;
        }

        .option-btn:hover {
          background: rgba(0, 170, 255, 0.12);
          border-color: var(--status-info, #00aaff);
        }

        .option-btn:active {
          background: rgba(0, 170, 255, 0.2);
        }

        .option-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-primary, #e0e0e0);
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .option-desc {
          font-size: 0.7rem;
          color: var(--text-secondary, #888899);
          line-height: 1.4;
        }

        /* Default option hint */
        .option-btn.is-default .option-label::after {
          content: " [DEFAULT]";
          color: var(--text-dim, #555566);
          font-weight: 400;
          font-size: 0.6rem;
        }

        /* Confirmation message */
        .confirmation {
          padding: 10px 12px;
          margin-bottom: 8px;
          border-radius: 4px;
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid rgba(0, 255, 136, 0.3);
          color: var(--status-nominal, #00ff88);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          text-align: center;
        }

        /* Resolved choices summary */
        .resolved-section {
          margin-top: 12px;
          padding-top: 10px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        .resolved-title {
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-dim, #555566);
          margin-bottom: 6px;
        }

        .resolved-entry {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--text-secondary, #888899);
          padding: 3px 0;
        }

        .resolved-choice-id {
          color: var(--text-dim, #555566);
        }

        .resolved-option {
          color: var(--status-nominal, #00ff88);
        }
      </style>

      <div id="choices-container" class="choices-container">
        <div class="no-choices">No active comms choices</div>
      </div>
    `;
  }

  _updateDisplay() {
    const container = this.shadowRoot.getElementById("choices-container");
    if (!container) return;

    const hasChoices = this._choices.length > 0;
    const hasResolved = Object.keys(this._resolved).length > 0;

    if (!hasChoices && !hasResolved && !this._confirmationMsg) {
      container.innerHTML = '<div class="no-choices">No active comms choices</div>';
      return;
    }

    let html = "";

    // Confirmation feedback
    if (this._confirmationMsg) {
      html += `<div class="confirmation">${this._escapeHtml(this._confirmationMsg)}</div>`;
    }

    // Active choices
    for (const choice of this._choices) {
      html += this._renderChoice(choice);
    }

    // No active but have resolved
    if (!hasChoices && hasResolved && !this._confirmationMsg) {
      html += '<div class="no-choices">No pending choices</div>';
    }

    // Resolved summary
    if (hasResolved) {
      html += '<div class="resolved-section">';
      html += '<div class="resolved-title">Previous Responses</div>';
      for (const [choiceId, optionId] of Object.entries(this._resolved)) {
        html += `<div class="resolved-entry">
          <span class="resolved-choice-id">${this._escapeHtml(choiceId)}</span>
          &rarr; <span class="resolved-option">${this._escapeHtml(optionId)}</span>
        </div>`;
      }
      html += "</div>";
    }

    container.innerHTML = html;

    // Bind option buttons
    for (const choice of this._choices) {
      for (const opt of choice.options) {
        const btn = this.shadowRoot.getElementById(`opt-${choice.choice_id}-${opt.option_id}`);
        if (btn) {
          btn.addEventListener("click", () => {
            this._respond(choice.choice_id, opt.option_id, opt.label);
          });
        }
      }
    }
  }

  _renderChoice(choice) {
    const contactLabel = choice.contact_id || "UNKNOWN";

    let timeoutHtml = "";
    if (choice.timeout != null && choice.presented_at != null) {
      const now = Date.now() / 1000;
      const elapsed = now - choice.presented_at;
      const remaining = Math.max(0, choice.timeout - elapsed);
      const pct = Math.max(0, Math.min(100, (remaining / choice.timeout) * 100));

      timeoutHtml = `
        <div class="timeout-section">
          <div class="timeout-track">
            <div class="timeout-fill" id="timeout-bar-${choice.choice_id}" style="width: ${pct}%"></div>
          </div>
          <span class="timeout-label" id="timeout-label-${choice.choice_id}">${Math.ceil(remaining)}s</span>
        </div>`;
    }

    const optionsHtml = choice.options.map(opt => {
      const isDefault = choice.default_option === opt.option_id;
      const defaultClass = isDefault ? " is-default" : "";
      const descHtml = opt.description
        ? `<span class="option-desc">${this._escapeHtml(opt.description)}</span>`
        : "";

      return `
        <button class="option-btn${defaultClass}" id="opt-${choice.choice_id}-${opt.option_id}">
          <span class="option-label">${this._escapeHtml(opt.label)}</span>
          ${descHtml}
        </button>`;
    }).join("");

    return `
      <div class="choice-card">
        <div class="choice-header">
          <div class="incoming-icon"></div>
          <span class="choice-contact">Incoming: ${this._escapeHtml(contactLabel)}</span>
        </div>
        <div class="choice-prompt">${this._escapeHtml(choice.prompt)}</div>
        ${timeoutHtml}
        <div class="options-list">
          ${optionsHtml}
        </div>
      </div>`;
  }

  _escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}

customElements.define("comms-choice-panel", CommsChoicePanel);
export { CommsChoicePanel };
