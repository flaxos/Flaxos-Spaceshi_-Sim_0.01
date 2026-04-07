/**
 * RCON Panel — hidden admin console for server control during UAT.
 *
 * Hidden by default. Activate with Ctrl+Shift+` (backtick) or by
 * setting window._showRcon = true before the component connects.
 *
 * Requires RCON authentication via password before commands work.
 */

import { wsClient } from "../js/ws-client.js";

class RconPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._visible = false;
    this._authenticated = false;
    this._status = null;
    this._log = [];
    this._scenarios = [];
  }

  connectedCallback() {
    this._render();
    this._keyHandler = (e) => {
      // Ctrl+Shift+` toggles visibility
      if (e.ctrlKey && e.shiftKey && e.key === "`") {
        e.preventDefault();
        this._visible = !this._visible;
        this._render();
        if (this._visible && !this._scenarios.length) {
          this._fetchScenarios();
        }
      }
    };
    document.addEventListener("keydown", this._keyHandler);

    // Allow programmatic show
    if (window._showRcon) {
      this._visible = true;
      this._render();
      this._fetchScenarios();
    }
  }

  disconnectedCallback() {
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  }

  _log_msg(msg) {
    const ts = new Date().toLocaleTimeString();
    this._log.unshift(`[${ts}] ${msg}`);
    if (this._log.length > 20) this._log.length = 20;
    this._updateLog();
  }

  _updateLog() {
    const el = this.shadowRoot.querySelector(".rcon-log");
    if (el) el.textContent = this._log.join("\n");
  }

  async _auth() {
    const input = this.shadowRoot.querySelector("#rcon-pw");
    const pw = input?.value || "";
    if (!pw) return;
    const resp = await wsClient.rconAuth(pw);
    if (resp?.ok) {
      this._authenticated = true;
      this._log_msg("Authenticated");
      input.value = "";
    } else {
      this._log_msg(`Auth failed: ${resp?.error || "unknown"}`);
    }
    this._render();
  }

  async _cmd(cmd, args = {}) {
    if (!this._authenticated) {
      this._log_msg("Not authenticated");
      return;
    }
    this._log_msg(`> ${cmd} ${JSON.stringify(args)}`);
    const resp = await wsClient.rcon(cmd, args);
    if (resp?.ok) {
      this._log_msg(`OK: ${JSON.stringify(resp).slice(0, 200)}`);
      if (cmd === "rcon_status") this._status = resp;
    } else {
      this._log_msg(`ERR: ${resp?.error || "unknown"}`);
    }
    this._render();
    return resp;
  }

  async _fetchScenarios() {
    try {
      const resp = await wsClient.send("list_scenarios", {});
      if (resp?.ok && resp.scenarios) {
        this._scenarios = resp.scenarios.map(s =>
          typeof s === "string" ? s : s.id || s.name || ""
        ).filter(Boolean).sort();
        this._render();
      }
    } catch (e) { /* ignore */ }
  }

  _render() {
    const host = this.shadowRoot;
    host.innerHTML = `
      <style>
        :host {
          position: fixed;
          top: 0;
          right: 0;
          z-index: 99999;
          font-family: "Fira Code", "Consolas", monospace;
          font-size: 11px;
        }
        .rcon-container {
          display: ${this._visible ? "flex" : "none"};
          flex-direction: column;
          width: 340px;
          max-height: 90vh;
          background: rgba(10, 10, 10, 0.95);
          border: 1px solid #333;
          border-right: none;
          border-top: none;
          color: #0f0;
          padding: 8px;
          gap: 6px;
          overflow-y: auto;
        }
        .rcon-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          color: #ff0;
          font-weight: bold;
          border-bottom: 1px solid #333;
          padding-bottom: 4px;
        }
        .rcon-close {
          cursor: pointer;
          color: #f44;
          background: none;
          border: none;
          font-size: 14px;
          font-family: inherit;
        }
        .rcon-auth {
          display: flex;
          gap: 4px;
        }
        .rcon-auth input {
          flex: 1;
          background: #111;
          border: 1px solid #333;
          color: #0f0;
          padding: 4px 6px;
          font-family: inherit;
          font-size: 11px;
        }
        .rcon-btn {
          background: #222;
          border: 1px solid #444;
          color: #0f0;
          padding: 4px 10px;
          cursor: pointer;
          font-family: inherit;
          font-size: 11px;
          white-space: nowrap;
        }
        .rcon-btn:hover { background: #333; }
        .rcon-btn:active { background: #0f0; color: #000; }
        .rcon-btn.danger { color: #f44; border-color: #f44; }
        .rcon-btn.danger:active { background: #f44; color: #000; }
        .rcon-group {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
        }
        .rcon-group-label {
          width: 100%;
          color: #888;
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-top: 2px;
        }
        .rcon-log {
          background: #0a0a0a;
          border: 1px solid #222;
          padding: 4px;
          max-height: 150px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-all;
          color: #0a0;
          font-size: 10px;
        }
        select {
          background: #111;
          border: 1px solid #333;
          color: #0f0;
          padding: 3px;
          font-family: inherit;
          font-size: 11px;
          flex: 1;
        }
        .rcon-status {
          color: #888;
          font-size: 10px;
        }
        .rcon-status span { color: #0f0; }
      </style>
      <div class="rcon-container">
        <div class="rcon-header">
          <span>SYS ADMIN</span>
          <button class="rcon-close" id="rcon-close">X</button>
        </div>

        ${!this._authenticated ? `
          <div class="rcon-auth">
            <input type="password" id="rcon-pw" placeholder="password" />
            <button class="rcon-btn" id="rcon-auth-btn">AUTH</button>
          </div>
        ` : `
          <div class="rcon-status">
            ${this._status ? `
              Scenario: <span>${this._status.scenario || "none"}</span> |
              Ships: <span>${this._status.ship_count || 0}</span> |
              Clients: <span>${this._status.client_count || 0}</span> |
              Tick: <span>${this._status.tick || 0}</span>
            ` : `<span style="color:#ff0">Authenticated</span> — press STATUS`}
          </div>

          <div class="rcon-group">
            <div class="rcon-group-label">Simulation</div>
            <button class="rcon-btn" id="btn-status">STATUS</button>
            <button class="rcon-btn" id="btn-pause">PAUSE</button>
            <button class="rcon-btn" id="btn-reload">RELOAD</button>
            <button class="rcon-btn danger" id="btn-restart">RESTART</button>
          </div>

          <div class="rcon-group">
            <div class="rcon-group-label">Time Scale</div>
            <button class="rcon-btn" id="btn-ts-05">0.5x</button>
            <button class="rcon-btn" id="btn-ts-1">1x</button>
            <button class="rcon-btn" id="btn-ts-2">2x</button>
            <button class="rcon-btn" id="btn-ts-5">5x</button>
          </div>

          <div class="rcon-group">
            <div class="rcon-group-label">Load Scenario</div>
            <select id="scenario-select">
              <option value="">-- select --</option>
              ${this._scenarios.map(s => `<option value="${s}">${s}</option>`).join("")}
            </select>
            <button class="rcon-btn" id="btn-load">LOAD</button>
          </div>
        `}

        <div class="rcon-log"></div>
      </div>
    `;

    // Wire events
    host.querySelector("#rcon-close")?.addEventListener("click", () => {
      this._visible = false;
      this._render();
    });

    host.querySelector("#rcon-auth-btn")?.addEventListener("click", () => this._auth());
    host.querySelector("#rcon-pw")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this._auth();
    });

    host.querySelector("#btn-status")?.addEventListener("click", () => this._cmd("rcon_status"));
    host.querySelector("#btn-pause")?.addEventListener("click", () => this._cmd("rcon_pause"));
    host.querySelector("#btn-reload")?.addEventListener("click", () => this._cmd("rcon_reload"));
    host.querySelector("#btn-restart")?.addEventListener("click", () => this._cmd("rcon_restart"));

    host.querySelector("#btn-ts-05")?.addEventListener("click", () => this._cmd("rcon_timescale", {scale: 0.5}));
    host.querySelector("#btn-ts-1")?.addEventListener("click", () => this._cmd("rcon_timescale", {scale: 1.0}));
    host.querySelector("#btn-ts-2")?.addEventListener("click", () => this._cmd("rcon_timescale", {scale: 2.0}));
    host.querySelector("#btn-ts-5")?.addEventListener("click", () => this._cmd("rcon_timescale", {scale: 5.0}));

    host.querySelector("#btn-load")?.addEventListener("click", () => {
      const sel = host.querySelector("#scenario-select");
      const scenario = sel?.value;
      if (scenario) this._cmd("rcon_load", {scenario});
    });

    this._updateLog();
  }
}

customElements.define("rcon-panel", RconPanel);
