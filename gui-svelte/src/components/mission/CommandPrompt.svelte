<script lang="ts">
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { playerShipId } from "../../lib/stores/playerShip.js";

  const KNOWN_COMMANDS = [
    "get_state", "get_events", "get_mission", "list_scenarios", "load_scenario",
    "list_ships", "station_status", "my_status", "assign_ship", "claim_station",
    "set_thrust", "set_orientation", "autopilot", "set_course", "ping_sensors",
    "lock_target", "unlock_target", "fire_railgun", "launch_torpedo", "launch_missile",
    "set_pdc_mode", "toggle_system", "set_power_allocation", "set_reactor_output",
    "helm_queue_status", "interrupt_helm_queue", "clear_helm_queue",
    "rotate", "set_angular_velocity", "point_at", "maneuver",
    "fleet_status", "fleet_form", "fleet_maneuver",
    "rcon_auth", "rcon_status", "rcon_pause", "rcon_reload",
  ];
  const SHIP_COMMANDS = new Set([
    "set_thrust", "set_orientation", "autopilot", "set_course", "ping_sensors",
    "lock_target", "unlock_target", "fire_railgun", "launch_torpedo", "launch_missile",
    "set_pdc_mode", "toggle_system", "set_power_allocation", "set_reactor_output",
    "helm_queue_status", "interrupt_helm_queue", "clear_helm_queue",
    "rotate", "set_angular_velocity", "point_at", "maneuver",
  ]);

  const STORAGE_KEY = "flaxos_command_history";
  const MAX_HISTORY = 50;

  // Output entries
  interface LogEntry { type: "input" | "output" | "error"; text: string; time: string; }

  let input = "";
  let log: LogEntry[] = [];
  let history: string[] = [];
  let historyIdx = -1;
  let savedInput = "";
  let suggestions: string[] = [];
  let inputEl: HTMLInputElement | undefined;

  // Load history from localStorage
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) history = JSON.parse(stored) as string[];
  } catch { /* ignore */ }

  function saveHistory() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); } catch { /* ignore */ }
  }

  function addLog(type: LogEntry["type"], text: string) {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    log = [...log.slice(-200), { type, text, time }];
    // Auto-scroll happens via DOM
  }

  function getSuggestions(val: string): string[] {
    if (!val.trim()) return [];
    const parts = val.trim().split(/\s+/);
    const cmd = parts[0];
    if (parts.length === 1) {
      return KNOWN_COMMANDS.filter(c => c.startsWith(cmd) && c !== cmd).slice(0, 6);
    }
    return [];
  }

  function onInput() {
    historyIdx = -1;
    suggestions = getSuggestions(input);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length === 0) return;
      if (historyIdx === -1) savedInput = input;
      historyIdx = Math.min(historyIdx + 1, history.length - 1);
      input = history[history.length - 1 - historyIdx];
      suggestions = [];
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIdx <= 0) { historyIdx = -1; input = savedInput; suggestions = getSuggestions(input); return; }
      historyIdx--;
      input = history[history.length - 1 - historyIdx];
    } else if (e.key === "Tab" && suggestions.length > 0) {
      e.preventDefault();
      input = suggestions[0] + " ";
      suggestions = [];
    } else if (e.key === "Enter") {
      submit();
    } else if (e.key === "Escape") {
      suggestions = [];
    }
  }

  function applySuggestion(s: string) {
    input = s + " ";
    suggestions = [];
    inputEl?.focus();
  }

  async function submit() {
    const line = input.trim();
    if (!line) return;

    // Push to history
    if (history[history.length - 1] !== line) {
      history = [...history, line];
      saveHistory();
    }
    historyIdx = -1;
    input = "";
    suggestions = [];

    addLog("input", `> ${line}`);

    // Parse: "cmd [{json}]" or "cmd key=value key=value"
    const parts = line.split(/\s+/);
    const cmd = parts[0];
    let params: Record<string, unknown> = {};

    const jsonPart = line.slice(cmd.length).trim();
    if (jsonPart.startsWith("{")) {
      try { params = JSON.parse(jsonPart); } catch { addLog("error", "Invalid JSON args"); return; }
    } else if (jsonPart) {
      // key=value pairs
      for (const kv of jsonPart.split(/\s+/)) {
        const [k, ...v] = kv.split("=");
        if (k && v.length) {
          const val = v.join("=");
          const num = parseFloat(val);
          params[k] = isNaN(num) ? (val === "true" ? true : val === "false" ? false : val) : num;
        }
      }
    }

    let currentShipId: string | null = null;
    playerShipId.subscribe(id => { currentShipId = id; })();

    if (SHIP_COMMANDS.has(cmd) && currentShipId && !params.ship) {
      params = { ...params, ship: currentShipId };
    }

    try {
      const resp = await wsClient.send(cmd, params);
      addLog("output", JSON.stringify(resp, null, 2));
    } catch (e) {
      addLog("error", `Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
</script>

<div class="prompt-root">
  <div class="log-area" aria-live="polite" aria-label="Command log">
    {#if log.length === 0}
      <div class="log-hint">Type a command and press Enter. Tab to autocomplete. ↑↓ for history.</div>
    {/if}
    {#each log as entry}
      <div class="log-entry log-{entry.type}">
        <span class="log-time">{entry.time}</span>
        <pre class="log-text">{entry.text}</pre>
      </div>
    {/each}
  </div>

  {#if suggestions.length > 0}
    <div class="suggestions">
      {#each suggestions as s}
        <button class="suggest-btn" on:click={() => applySuggestion(s)}>{s}</button>
      {/each}
    </div>
  {/if}

  <div class="input-row">
    <span class="prompt-prefix">&gt;</span>
    <input
      bind:this={inputEl}
      class="prompt-input"
      type="text"
      placeholder="command [args...]"
      spellcheck="false"
      autocomplete="off"
      bind:value={input}
      on:input={onInput}
      on:keydown={onKeydown}
    />
  </div>
</div>

<style>
  .prompt-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
  }

  .log-area {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-xs);
    min-height: 0;
    background: var(--bg-void);
  }

  .log-hint {
    color: var(--text-dim);
    padding: var(--space-xs);
    font-style: italic;
  }

  .log-entry {
    display: flex;
    gap: var(--space-xs);
    margin-bottom: 2px;
    align-items: flex-start;
  }

  .log-time {
    color: var(--text-dim);
    font-size: 0.6rem;
    flex-shrink: 0;
    margin-top: 1px;
  }

  .log-text {
    flex: 1;
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: inherit;
    font-size: inherit;
    line-height: 1.4;
  }

  .log-input .log-text { color: var(--tier-accent, var(--hud-primary)); }
  .log-output .log-text { color: var(--text-primary); }
  .log-error .log-text { color: var(--status-critical); }

  .suggestions {
    display: flex;
    gap: 4px;
    padding: 4px var(--space-xs);
    background: var(--bg-input);
    flex-wrap: wrap;
  }

  .suggest-btn {
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--tier-accent, var(--hud-primary));
    font-family: var(--font-mono);
    font-size: 0.6rem;
    padding: 2px 8px;
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .suggest-btn:hover { background: var(--bg-hover); }

  .input-row {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    padding: var(--space-xs);
    background: var(--bg-input);
    border-top: 1px solid var(--border-default);
  }

  .prompt-prefix {
    color: var(--tier-accent, var(--hud-primary));
    font-weight: 700;
    user-select: none;
  }

  .prompt-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    caret-color: var(--tier-accent, var(--hud-primary));
  }
</style>
