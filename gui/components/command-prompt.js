/**
 * Command Prompt Component
 * Text input with command history and autocomplete
 */

import { wsClient } from "../js/ws-client.js";

// Server command names (corrected to match backend)
const KNOWN_COMMANDS = [
  // Global commands (no ship required)
  "get_state",
  "get_events",
  "get_mission",
  "get_mission_hints",
  "list_scenarios",
  "load_scenario",
  "pause",
  // Ship-specific commands (require ship parameter)
  "set_thrust",          // Scalar throttle (0-1) for main drive
  "set_thrust_vector",   // Debug: arbitrary XYZ thrust
  "set_orientation",     // Attitude target (RCS maneuvers to achieve)
  "ping_sensors",
  "lock_target",
  "unlock_target",
  "autopilot",
  "fire_weapon",
  "toggle_system",
];

// Commands that need ship parameter
const SHIP_COMMANDS = new Set([
  "set_thrust",
  "set_thrust_vector",
  "set_orientation",
  "ping_sensors",
  "lock_target",
  "unlock_target",
  "autopilot",
  "fire_weapon",
  "toggle_system",
]);

const MAX_HISTORY = 50;
const STORAGE_KEY = "flaxos_command_history";

class CommandPrompt extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._history = [];
    this._historyIndex = -1;
    this._currentInput = "";
    this._suggestions = [];
    this._selectedSuggestion = -1;
  }

  connectedCallback() {
    this._loadHistory();
    this.render();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.85rem;
        }

        .prompt-container {
          display: flex;
          flex-direction: column;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 8px;
          overflow: hidden;
        }

        .input-row {
          display: flex;
          align-items: center;
          padding: 12px 16px;
          gap: 8px;
        }

        .prompt-symbol {
          color: var(--status-info, #00aaff);
          font-weight: bold;
          flex-shrink: 0;
        }

        .prompt-input {
          flex: 1;
          background: transparent;
          border: none;
          color: var(--text-primary, #e0e0e0);
          font-family: inherit;
          font-size: inherit;
          outline: none;
          padding: 0;
        }

        .prompt-input::placeholder {
          color: var(--text-dim, #555566);
        }

        .submit-btn {
          background: var(--status-info, #00aaff);
          border: none;
          color: #000;
          padding: 6px 12px;
          border-radius: 4px;
          cursor: pointer;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.75rem;
          font-weight: 600;
          min-height: auto;
        }

        .submit-btn:hover {
          opacity: 0.9;
        }

        .submit-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .suggestions {
          display: none;
          border-top: 1px solid var(--border-default, #2a2a3a);
          max-height: 150px;
          overflow-y: auto;
        }

        .suggestions.active {
          display: block;
        }

        .suggestion {
          padding: 8px 16px;
          cursor: pointer;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .suggestion:hover,
        .suggestion.selected {
          background: rgba(255, 255, 255, 0.05);
        }

        .suggestion-cmd {
          color: var(--text-primary, #e0e0e0);
        }

        .suggestion-hint {
          color: var(--text-dim, #555566);
          font-size: 0.75rem;
        }

        .help-text {
          padding: 8px 16px;
          border-top: 1px solid var(--border-default, #2a2a3a);
          color: var(--text-dim, #555566);
          font-size: 0.7rem;
          display: flex;
          gap: 16px;
        }

        .help-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .key {
          background: rgba(255, 255, 255, 0.1);
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 0.65rem;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 0.7rem;
        }

        .status-indicator.success {
          color: var(--status-nominal, #00ff88);
        }

        .status-indicator.error {
          color: var(--status-critical, #ff4444);
        }

        .status-indicator.pending {
          color: var(--status-warning, #ffaa00);
        }
      </style>

      <div class="prompt-container">
        <div class="input-row">
          <span class="prompt-symbol">></span>
          <input 
            type="text" 
            class="prompt-input" 
            id="input"
            placeholder="Enter command (Tab: autocomplete, ↑↓: history)"
            autocomplete="off"
            spellcheck="false"
          >
          <span class="status-indicator" id="status"></span>
          <button class="submit-btn" id="submit-btn">Send</button>
        </div>
        <div class="suggestions" id="suggestions"></div>
        <div class="help-text">
          <span class="help-item"><span class="key">↑/↓</span> History</span>
          <span class="help-item"><span class="key">Tab</span> Autocomplete</span>
          <span class="help-item"><span class="key">Enter</span> Send</span>
          <span class="help-item"><span class="key">Esc</span> Clear</span>
        </div>
      </div>
    `;

    this._setupEvents();
  }

  _setupEvents() {
    const input = this.shadowRoot.getElementById("input");
    const submitBtn = this.shadowRoot.getElementById("submit-btn");
    const suggestions = this.shadowRoot.getElementById("suggestions");

    input.addEventListener("keydown", (e) => this._handleKeyDown(e));
    input.addEventListener("input", () => this._handleInput());
    input.addEventListener("blur", () => {
      // Delay hiding suggestions to allow clicking
      setTimeout(() => this._hideSuggestions(), 150);
    });

    submitBtn.addEventListener("click", () => this._submit());

    suggestions.addEventListener("click", (e) => {
      const suggestion = e.target.closest(".suggestion");
      if (suggestion) {
        this._selectSuggestion(suggestion.dataset.cmd);
      }
    });
  }

  _handleKeyDown(e) {
    const input = this.shadowRoot.getElementById("input");

    switch (e.key) {
      case "Enter":
        e.preventDefault();
        if (this._selectedSuggestion >= 0 && this._suggestions.length > 0) {
          this._selectSuggestion(this._suggestions[this._selectedSuggestion]);
        } else {
          this._submit();
        }
        break;

      case "ArrowUp":
        e.preventDefault();
        if (this._suggestions.length > 0 && this._selectedSuggestion > 0) {
          this._selectedSuggestion--;
          this._renderSuggestions();
        } else {
          this._navigateHistory(-1);
        }
        break;

      case "ArrowDown":
        e.preventDefault();
        if (this._suggestions.length > 0 && this._selectedSuggestion < this._suggestions.length - 1) {
          this._selectedSuggestion++;
          this._renderSuggestions();
        } else {
          this._navigateHistory(1);
        }
        break;

      case "Tab":
        e.preventDefault();
        if (this._suggestions.length > 0) {
          const cmd = this._suggestions[Math.max(0, this._selectedSuggestion)];
          this._selectSuggestion(cmd);
        } else {
          this._showAllSuggestions();
        }
        break;

      case "Escape":
        e.preventDefault();
        if (this._suggestions.length > 0) {
          this._hideSuggestions();
        } else {
          input.value = "";
          this._historyIndex = -1;
          this._currentInput = "";
        }
        break;
    }
  }

  _handleInput() {
    const input = this.shadowRoot.getElementById("input");
    const value = input.value.trim();

    this._currentInput = value;
    this._historyIndex = -1;

    if (value.length > 0) {
      this._updateSuggestions(value);
    } else {
      this._hideSuggestions();
    }
  }

  _updateSuggestions(query) {
    const words = query.toLowerCase().split(/\s+/);
    const firstWord = words[0];

    // Only suggest if typing the first word (command name)
    if (words.length === 1) {
      this._suggestions = KNOWN_COMMANDS.filter(cmd =>
        cmd.toLowerCase().startsWith(firstWord)
      );
    } else {
      this._suggestions = [];
    }

    this._selectedSuggestion = -1;
    this._renderSuggestions();
  }

  _showAllSuggestions() {
    this._suggestions = [...KNOWN_COMMANDS];
    this._selectedSuggestion = -1;
    this._renderSuggestions();
  }

  _renderSuggestions() {
    const container = this.shadowRoot.getElementById("suggestions");

    if (this._suggestions.length === 0) {
      container.classList.remove("active");
      return;
    }

    container.classList.add("active");
    container.innerHTML = this._suggestions.map((cmd, i) => `
      <div class="suggestion ${i === this._selectedSuggestion ? "selected" : ""}" data-cmd="${cmd}">
        <span class="suggestion-cmd">${cmd}</span>
        <span class="suggestion-hint">${this._getCommandHint(cmd)}</span>
      </div>
    `).join("");
  }

  _getCommandHint(cmd) {
    const hints = {
      set_thrust: "<throttle 0-1>",
      set_thrust_vector: "<x> <y> <z> (debug)",
      set_orientation: "<pitch> <yaw> [roll]",
      lock_target: "<contact_id>",
      autopilot: "<program> [target]",
      fire_weapon: "<weapon_type>",
      toggle_system: "<system> <0|1>",
      load_scenario: "<scenario_name>",
      get_state: "[ship_id]",
    };
    return hints[cmd] || "";
  }

  _hideSuggestions() {
    const container = this.shadowRoot.getElementById("suggestions");
    container.classList.remove("active");
    this._suggestions = [];
    this._selectedSuggestion = -1;
  }

  _selectSuggestion(cmd) {
    const input = this.shadowRoot.getElementById("input");
    input.value = cmd + " ";
    input.focus();
    this._hideSuggestions();
    this._currentInput = input.value;
  }

  _navigateHistory(direction) {
    if (this._history.length === 0) return;

    const input = this.shadowRoot.getElementById("input");

    // Save current input before navigating
    if (this._historyIndex === -1 && direction === -1) {
      this._currentInput = input.value;
    }

    // Calculate new index
    let newIndex = this._historyIndex + direction;
    newIndex = Math.max(-1, Math.min(this._history.length - 1, newIndex));

    if (newIndex !== this._historyIndex) {
      this._historyIndex = newIndex;

      if (newIndex === -1) {
        input.value = this._currentInput;
      } else {
        input.value = this._history[this._history.length - 1 - newIndex];
      }

      // Move cursor to end
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  async _submit() {
    const input = this.shadowRoot.getElementById("input");
    const status = this.shadowRoot.getElementById("status");
    const value = input.value.trim();

    if (!value) return;

    // Add to history
    this._addToHistory(value);

    // Parse command
    let cmd, args;
    try {
      if (value.startsWith("{")) {
        // JSON format
        const parsed = JSON.parse(value);
        cmd = parsed.cmd || parsed.command;
        args = parsed;
        delete args.cmd;
        delete args.command;
      } else {
        // Space-separated format: "cmd arg1 arg2"
        const parts = value.split(/\s+/);
        cmd = parts[0];
        args = {};

        // Parse arguments based on command
        if (parts.length > 1) {
          const argStr = parts.slice(1).join(" ");

          // Try to parse as JSON first
          try {
            args = JSON.parse(argStr);
          } catch {
            // Fallback to positional args based on command
            if (cmd === "set_thrust") {
              // Scalar throttle (0-1) for main drive
              args.thrust = parseFloat(parts[1] || 0);
            } else if (cmd === "set_thrust_vector") {
              // Debug: arbitrary vector thrust
              args.x = parseFloat(parts[1] || 0);
              args.y = parseFloat(parts[2] || 0);
              args.z = parseFloat(parts[3] || 0);
            } else if (cmd === "set_orientation") {
              args.pitch = parseFloat(parts[1] || 0);
              args.yaw = parseFloat(parts[2] || 0);
              args.roll = parseFloat(parts[3] || 0);
            } else if (cmd === "lock_target") {
              args.target_id = parts[1];
            } else if (cmd === "load_scenario") {
              args.scenario = parts[1];
            } else if (cmd === "autopilot") {
              args.program = parts[1];
              if (parts[2]) args.target = parts[2];
            } else if (cmd === "fire_weapon") {
              args.weapon_type = parts[1];
            } else if (cmd === "toggle_system") {
              args.system = parts[1];
              args.state = parseInt(parts[2] || "1", 10);
            } else if (cmd === "get_state" && parts[1]) {
              args.ship = parts[1];
            } else {
              args.args = argStr;
            }
          }
        }
      }
    } catch (error) {
      status.textContent = "✕ Parse error";
      status.className = "status-indicator error";
      return;
    }

    // Show pending status
    status.textContent = "⋯";
    status.className = "status-indicator pending";

    // Dispatch command event
    this.dispatchEvent(new CustomEvent("command", {
      detail: { cmd, args, raw: value },
      bubbles: true
    }));

    // Send to server - use sendShipCommand for ship-specific commands
    try {
      let response;
      if (SHIP_COMMANDS.has(cmd)) {
        response = await wsClient.sendShipCommand(cmd, args);
      } else {
        response = await wsClient.send(cmd, args);
      }

      if (response && response.ok !== false) {
        status.textContent = "✓";
        status.className = "status-indicator success";
      } else {
        status.textContent = "✕";
        status.className = "status-indicator error";
      }
    } catch (error) {
      status.textContent = "✕ " + error.message;
      status.className = "status-indicator error";
    }

    // Clear input
    input.value = "";
    this._historyIndex = -1;
    this._currentInput = "";

    // Clear status after delay
    setTimeout(() => {
      status.textContent = "";
      status.className = "status-indicator";
    }, 3000);
  }

  _addToHistory(command) {
    // Don't add duplicates consecutively
    if (this._history.length > 0 && this._history[this._history.length - 1] === command) {
      return;
    }

    this._history.push(command);

    // Limit history size
    while (this._history.length > MAX_HISTORY) {
      this._history.shift();
    }

    this._saveHistory();
  }

  _loadHistory() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        this._history = JSON.parse(stored);
      }
    } catch {
      this._history = [];
    }
  }

  _saveHistory() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this._history));
    } catch {
      // Ignore storage errors
    }
  }

  /**
   * Focus the input
   */
  focus() {
    const input = this.shadowRoot.getElementById("input");
    input?.focus();
  }

  /**
   * Clear history
   */
  clearHistory() {
    this._history = [];
    this._saveHistory();
  }
}

customElements.define("command-prompt", CommandPrompt);
export { CommandPrompt };
