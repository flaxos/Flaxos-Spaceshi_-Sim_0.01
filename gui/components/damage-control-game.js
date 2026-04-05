/**
 * Damage Control Game (ARCADE tier)
 *
 * Pipe-routing puzzle for subsystem repair. When a subsystem takes damage,
 * the player connects power conduits from the reactor to the damaged system
 * through a grid. Complexity scales with damage severity. Time pressure from
 * cascading failures.
 *
 * Reads subsystem health from stateManager. On puzzle completion, sends
 * dispatch_repair command to the server. The GUI is display + input only;
 * all actual repair state lives on the server.
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

// --- Pipe types and their open sides ---
// Each pipe type defines which sides are open: [top, right, bottom, left]
const PIPE_TYPES = {
  empty:    [false, false, false, false],
  h_pipe:   [false, true,  false, true],   // horizontal straight
  v_pipe:   [true,  false, true,  false],   // vertical straight
  corner_0: [true,  true,  false, false],   // top-right corner
  corner_1: [false, true,  true,  false],   // right-bottom corner
  corner_2: [false, false, true,  true],    // bottom-left corner
  corner_3: [true,  false, false, true],    // left-top corner
  t_up:     [true,  true,  false, true],    // T-junction, no bottom
  t_right:  [true,  true,  true,  false],   // T-junction, no left
  t_down:   [false, true,  true,  true],    // T-junction, no top
  t_left:   [true,  false, true,  true],    // T-junction, no right
  cross:    [true,  true,  true,  true],    // 4-way cross
};

// Click cycle: place straight, then rotate through all useful types
const CLICK_CYCLE = [
  "h_pipe", "v_pipe",
  "corner_0", "corner_1", "corner_2", "corner_3",
  "t_up", "t_right", "t_down", "t_left",
  "cross",
];

const SUBSYSTEM_LABELS = {
  reactor: "REACTOR",
  propulsion: "DRIVE",
  rcs: "RCS",
  sensors: "SENSORS",
  targeting: "TARGETING",
  weapons: "WEAPONS",
  life_support: "LIFE SPT",
  radiators: "RADIATORS",
};

// SVG path data for each pipe type (drawn in a 40x40 viewBox, centered at 20,20)
function pipeSVG(type, connected) {
  const sides = PIPE_TYPES[type];
  if (!sides) return "";
  const color = connected ? "#00ff88" : "#4488ff";
  const glow = connected ? "drop-shadow(0 0 3px #00ff88)" : "none";
  let paths = "";
  // Draw lines from center to each open side
  if (sides[0]) paths += `<line x1="20" y1="0" x2="20" y2="20"/>`; // top
  if (sides[1]) paths += `<line x1="20" y1="20" x2="40" y2="20"/>`; // right
  if (sides[2]) paths += `<line x1="20" y1="20" x2="20" y2="40"/>`; // bottom
  if (sides[3]) paths += `<line x1="0" y1="20" x2="20" y2="20"/>`; // left
  // Center node
  paths += `<circle cx="20" cy="20" r="3" fill="${color}"/>`;
  return `<svg viewBox="0 0 40 40" style="width:100%;height:100%;filter:${glow}">
    <g stroke="${color}" stroke-width="3" stroke-linecap="round">${paths}</g>
  </svg>`;
}

class DamageControlGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._grid = [];       // 2D array: _grid[y][x] = { type, blocked }
    this._gridWidth = 6;
    this._gridHeight = 4;
    this._source = { x: 0, y: 1 };
    this._target = { x: 5, y: 2 };
    this._timer = 30;
    this._timerMax = 30;
    this._timerInterval = null;
    this._activeSubsystem = null;
    this._solved = false;
    this._connectedSet = new Set(); // "x,y" keys of connected cells
    this._previousStatuses = {};    // track subsystem status transitions
    this._unsub = null;
    this._puzzleQueue = [];         // subsystems waiting for puzzle
    this._completionFlashTimer = null;
  }

  connectedCallback() {
    this._render();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }
    if (this._completionFlashTimer) {
      clearTimeout(this._completionFlashTimer);
      this._completionFlashTimer = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => this._onStateUpdate());
  }

  /** Check subsystem health and trigger puzzles on damage transitions */
  _onStateUpdate() {
    const ship = stateManager.getShipState();
    if (!ship?.subsystem_health?.subsystems) return;

    const subs = ship.subsystem_health.subsystems;
    for (const [name, report] of Object.entries(subs)) {
      const status = (report.status || "online").toLowerCase();
      const prev = this._previousStatuses[name];
      this._previousStatuses[name] = status;

      // Trigger puzzle when a subsystem transitions to a damaged state
      if (prev && prev === "online" && status !== "online" && status !== "nominal") {
        const health = report.health_percent ?? 100;
        this._queuePuzzle(name, health);
      }
    }

    // If no active puzzle, try starting from queue
    if (!this._activeSubsystem && this._puzzleQueue.length > 0) {
      const next = this._puzzleQueue.shift();
      this._startPuzzle(next.subsystem, next.health);
    }

    // Update idle state display
    if (!this._activeSubsystem) {
      this._renderIdleState(subs);
    }
  }

  _queuePuzzle(subsystem, health) {
    // Don't queue duplicates
    if (this._activeSubsystem === subsystem) return;
    if (this._puzzleQueue.some(p => p.subsystem === subsystem)) return;
    this._puzzleQueue.push({ subsystem, health });

    // If no active puzzle, start immediately
    if (!this._activeSubsystem) {
      const next = this._puzzleQueue.shift();
      this._startPuzzle(next.subsystem, next.health);
    }
  }

  /** Start a new puzzle for the given subsystem */
  _startPuzzle(subsystem, health) {
    this._activeSubsystem = subsystem;
    this._solved = false;
    this._connectedSet.clear();

    // Difficulty scaling based on health
    if (health > 60) {
      // Minor damage
      this._gridWidth = 6;
      this._gridHeight = 3;
      this._timer = 30;
      this._timerMax = 30;
    } else if (health > 30) {
      // Moderate damage
      this._gridWidth = 6;
      this._gridHeight = 4;
      this._timer = 20;
      this._timerMax = 20;
    } else {
      // Critical damage
      this._gridWidth = 6;
      this._gridHeight = 5;
      this._timer = 15;
      this._timerMax = 15;
    }

    // Source on left edge, target on right edge (vertically centered-ish)
    this._source = { x: 0, y: Math.floor(this._gridHeight / 2) };
    this._target = { x: this._gridWidth - 1, y: Math.floor(this._gridHeight / 2) };

    this._initGrid(health);
    this._renderPuzzle();
    this._startTimer();
  }

  /** Initialize grid with blocked cells based on difficulty */
  _initGrid(health) {
    this._grid = [];
    // Number of blocked cells scales with damage severity
    let blockedCount;
    if (health > 60) {
      blockedCount = 2;
    } else if (health > 30) {
      blockedCount = 4;
    } else {
      blockedCount = 7;
    }

    // Create empty grid
    for (let y = 0; y < this._gridHeight; y++) {
      const row = [];
      for (let x = 0; x < this._gridWidth; x++) {
        row.push({ type: "empty", blocked: false });
      }
      this._grid.push(row);
    }

    // Place source and target (these are pre-placed pipes, not user-editable)
    this._grid[this._source.y][this._source.x] = { type: "h_pipe", blocked: false, fixed: true };
    this._grid[this._target.y][this._target.x] = { type: "h_pipe", blocked: false, fixed: true };

    // Randomly block cells (never block source/target or their neighbors)
    const protectedCells = new Set();
    protectedCells.add(`${this._source.x},${this._source.y}`);
    protectedCells.add(`${this._target.x},${this._target.y}`);
    // Protect cells adjacent to source and target
    for (const node of [this._source, this._target]) {
      for (const [dx, dy] of [[0,-1],[0,1],[1,0],[-1,0]]) {
        const nx = node.x + dx;
        const ny = node.y + dy;
        if (nx >= 0 && nx < this._gridWidth && ny >= 0 && ny < this._gridHeight) {
          protectedCells.add(`${nx},${ny}`);
        }
      }
    }

    let placed = 0;
    let attempts = 0;
    while (placed < blockedCount && attempts < 100) {
      const bx = Math.floor(Math.random() * this._gridWidth);
      const by = Math.floor(Math.random() * this._gridHeight);
      const key = `${bx},${by}`;
      if (!protectedCells.has(key) && !this._grid[by][bx].blocked) {
        this._grid[by][bx] = { type: "empty", blocked: true };
        placed++;
      }
      attempts++;
    }
  }

  _startTimer() {
    if (this._timerInterval) clearInterval(this._timerInterval);
    this._timerInterval = setInterval(() => {
      this._timer -= 1;
      this._updateTimerBar();
      if (this._timer <= 0) {
        this._onTimerExpired();
      }
    }, 1000);
  }

  _onTimerExpired() {
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }
    // Flash the grid red to indicate failure
    const gridEl = this.shadowRoot.getElementById("puzzle-grid");
    if (gridEl) {
      gridEl.classList.add("failure-flash");
    }
    // Show failure text
    const statusEl = this.shadowRoot.getElementById("puzzle-status");
    if (statusEl) {
      statusEl.textContent = "REPAIR FAILED - ADDITIONAL DEGRADATION";
      statusEl.className = "puzzle-status failure";
    }
    // Clear after a moment and move to next puzzle or idle
    this._completionFlashTimer = setTimeout(() => {
      this._activeSubsystem = null;
      this._renderPuzzle();
      if (this._puzzleQueue.length > 0) {
        const next = this._puzzleQueue.shift();
        this._startPuzzle(next.subsystem, next.health);
      } else {
        this._renderIdleState();
      }
    }, 2000);
  }

  _onPuzzleSolved() {
    this._solved = true;
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }

    // Send repair command to server
    wsClient.sendShipCommand("dispatch_repair", {
      target: this._activeSubsystem,
    }).catch(err => {
      console.warn("dispatch_repair failed:", err.message);
    });

    // Show success state
    const statusEl = this.shadowRoot.getElementById("puzzle-status");
    if (statusEl) {
      statusEl.textContent = "REPAIR DISPATCHED";
      statusEl.className = "puzzle-status success";
    }

    // Flow animation on the connected path
    const gridEl = this.shadowRoot.getElementById("puzzle-grid");
    if (gridEl) {
      gridEl.classList.add("solved-glow");
    }

    // Clear after animation and move to next
    this._completionFlashTimer = setTimeout(() => {
      this._activeSubsystem = null;
      if (this._puzzleQueue.length > 0) {
        const next = this._puzzleQueue.shift();
        this._startPuzzle(next.subsystem, next.health);
      } else {
        this._renderIdleState();
      }
    }, 2000);
  }

  /** Handle left-click: place or cycle pipe */
  _onCellClick(x, y) {
    if (this._solved) return;
    const cell = this._grid[y]?.[x];
    if (!cell || cell.blocked || cell.fixed) return;

    if (cell.type === "empty") {
      // Place first pipe type
      cell.type = CLICK_CYCLE[0];
    } else {
      // Cycle to next type
      const idx = CLICK_CYCLE.indexOf(cell.type);
      const nextIdx = (idx + 1) % CLICK_CYCLE.length;
      cell.type = CLICK_CYCLE[nextIdx];
    }

    this._validatePath();
    this._renderGridCells();
  }

  /** Handle right-click: remove pipe */
  _onCellRightClick(x, y, e) {
    e.preventDefault();
    if (this._solved) return;
    const cell = this._grid[y]?.[x];
    if (!cell || cell.blocked || cell.fixed) return;

    cell.type = "empty";
    this._validatePath();
    this._renderGridCells();
  }

  /** BFS from source to find all connected cells and check if target is reached */
  _validatePath() {
    this._connectedSet.clear();
    const visited = new Set();
    const queue = [`${this._source.x},${this._source.y}`];
    visited.add(queue[0]);

    // Direction deltas: [top, right, bottom, left] -> [dx, dy]
    const DIR_DELTA = [
      [0, -1], // top
      [1, 0],  // right
      [0, 1],  // bottom
      [-1, 0], // left
    ];
    // Opposite side index
    const OPPOSITE = [2, 3, 0, 1];

    while (queue.length > 0) {
      const key = queue.shift();
      const [cx, cy] = key.split(",").map(Number);
      const cell = this._grid[cy]?.[cx];
      if (!cell || cell.blocked || cell.type === "empty") continue;

      const sides = PIPE_TYPES[cell.type];
      if (!sides) continue;

      this._connectedSet.add(key);

      for (let dir = 0; dir < 4; dir++) {
        if (!sides[dir]) continue; // this side is closed
        const [dx, dy] = DIR_DELTA[dir];
        const nx = cx + dx;
        const ny = cy + dy;
        const nkey = `${nx},${ny}`;

        if (nx < 0 || nx >= this._gridWidth || ny < 0 || ny >= this._gridHeight) continue;
        if (visited.has(nkey)) continue;

        const neighbor = this._grid[ny]?.[nx];
        if (!neighbor || neighbor.blocked || neighbor.type === "empty") continue;

        const nSides = PIPE_TYPES[neighbor.type];
        if (!nSides) continue;

        // Check that the neighbor's opposite side is also open
        if (nSides[OPPOSITE[dir]]) {
          visited.add(nkey);
          queue.push(nkey);
        }
      }
    }

    // Check if target is in connected set
    const targetKey = `${this._target.x},${this._target.y}`;
    if (this._connectedSet.has(targetKey)) {
      this._onPuzzleSolved();
    }
  }

  _updateTimerBar() {
    const bar = this.shadowRoot.getElementById("timer-fill");
    const label = this.shadowRoot.getElementById("timer-label");
    if (!bar || !label) return;

    const pct = Math.max(0, (this._timer / this._timerMax) * 100);
    bar.style.width = `${pct}%`;
    label.textContent = `${this._timer}s`;

    // Color transition: green -> yellow -> red
    if (pct > 50) {
      bar.style.background = `linear-gradient(90deg, #00cc44, #44ee88)`;
    } else if (pct > 25) {
      bar.style.background = `linear-gradient(90deg, #ccaa00, #eecc44)`;
    } else {
      bar.style.background = `linear-gradient(90deg, #cc2200, #ee4422)`;
      bar.classList.add("urgent");
    }
  }

  // --- Rendering ---

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${this._getStyles()}</style>
      <div class="dc-container" id="dc-container">
        <div class="idle-state" id="idle-state">
          <div class="idle-icon">&#x2699;</div>
          <div class="idle-text">DAMAGE CONTROL STANDBY</div>
          <div class="idle-subtext">Pipe routing puzzles appear when subsystems take damage</div>
        </div>
      </div>
    `;
  }

  _renderIdleState(subs) {
    const container = this.shadowRoot.getElementById("dc-container");
    if (!container) return;

    // Check if any subsystems are currently damaged
    const damaged = [];
    if (subs) {
      for (const [name, report] of Object.entries(subs)) {
        const status = (report.status || "online").toLowerCase();
        if (status !== "online" && status !== "nominal") {
          damaged.push(name);
        }
      }
    }

    const damageInfo = damaged.length > 0
      ? `<div class="idle-damaged">${damaged.length} subsystem${damaged.length > 1 ? "s" : ""} damaged: ${damaged.map(d => SUBSYSTEM_LABELS[d] || d.toUpperCase()).join(", ")}</div>`
      : "";

    container.innerHTML = `
      <div class="idle-state" id="idle-state">
        <div class="idle-icon">&#x2699;</div>
        <div class="idle-text">DAMAGE CONTROL STANDBY</div>
        <div class="idle-subtext">Pipe routing puzzles appear when subsystems take damage</div>
        ${damageInfo}
        ${damaged.length > 0 ? `<button class="manual-start-btn" id="manual-start-btn">START REPAIR: ${SUBSYSTEM_LABELS[damaged[0]] || damaged[0].toUpperCase()}</button>` : ""}
      </div>
    `;

    // Wire manual start button for already-damaged subsystems
    if (damaged.length > 0) {
      const btn = this.shadowRoot.getElementById("manual-start-btn");
      if (btn) {
        btn.addEventListener("click", () => {
          const sub = damaged[0];
          const health = subs[sub]?.health_percent ?? 50;
          this._startPuzzle(sub, health);
        });
      }
    }
  }

  _renderPuzzle() {
    const container = this.shadowRoot.getElementById("dc-container");
    if (!container) return;

    if (!this._activeSubsystem) {
      this._renderIdleState();
      return;
    }

    const label = SUBSYSTEM_LABELS[this._activeSubsystem] || this._activeSubsystem.toUpperCase();

    container.innerHTML = `
      <div class="puzzle-header">
        <span class="puzzle-title">REROUTE POWER TO: <strong>${label}</strong></span>
        <span class="puzzle-status" id="puzzle-status">Connect reactor to subsystem</span>
      </div>
      <div class="timer-bar">
        <div class="timer-fill" id="timer-fill" style="width: 100%"></div>
        <span class="timer-label" id="timer-label">${this._timer}s</span>
      </div>
      <div class="puzzle-grid" id="puzzle-grid"
           style="grid-template-columns: repeat(${this._gridWidth}, 1fr);
                  grid-template-rows: repeat(${this._gridHeight}, 1fr);">
      </div>
      <div class="puzzle-legend">
        <span class="legend-item"><span class="legend-color source"></span>PWR</span>
        <span class="legend-item"><span class="legend-color target"></span>${label}</span>
        <span class="legend-hint">Click: place/cycle | Right-click: remove</span>
      </div>
    `;

    this._renderGridCells();
  }

  _renderGridCells() {
    const gridEl = this.shadowRoot.getElementById("puzzle-grid");
    if (!gridEl) return;

    gridEl.innerHTML = "";

    for (let y = 0; y < this._gridHeight; y++) {
      for (let x = 0; x < this._gridWidth; x++) {
        const cell = this._grid[y][x];
        const div = document.createElement("div");
        div.className = "grid-cell";
        const isSource = x === this._source.x && y === this._source.y;
        const isTarget = x === this._target.x && y === this._target.y;
        const isConnected = this._connectedSet.has(`${x},${y}`);

        if (cell.blocked) {
          div.classList.add("blocked");
          div.innerHTML = `<svg viewBox="0 0 40 40" style="width:100%;height:100%">
            <line x1="8" y1="8" x2="32" y2="32" stroke="#2a2a3a" stroke-width="2"/>
            <line x1="32" y1="8" x2="8" y2="32" stroke="#2a2a3a" stroke-width="2"/>
          </svg>`;
        } else if (isSource) {
          div.classList.add("source");
          div.innerHTML = `<div class="node-label">PWR</div>` + pipeSVG(cell.type, isConnected);
        } else if (isTarget) {
          div.classList.add("target");
          const label = SUBSYSTEM_LABELS[this._activeSubsystem] || "SYS";
          div.innerHTML = `<div class="node-label target-label">${label}</div>` + pipeSVG(cell.type, isConnected);
        } else if (cell.type !== "empty") {
          div.innerHTML = pipeSVG(cell.type, isConnected);
          if (isConnected) div.classList.add("connected");
        }

        if (!cell.blocked && !cell.fixed) {
          div.addEventListener("click", () => this._onCellClick(x, y));
          div.addEventListener("contextmenu", (e) => this._onCellRightClick(x, y, e));
          // Long-press for mobile: remove pipe
          let longPressTimer = null;
          div.addEventListener("touchstart", (e) => {
            longPressTimer = setTimeout(() => {
              e.preventDefault();
              this._onCellRightClick(x, y, e);
            }, 500);
          }, { passive: false });
          div.addEventListener("touchend", () => {
            if (longPressTimer) {
              clearTimeout(longPressTimer);
              longPressTimer = null;
            }
          });
        }

        gridEl.appendChild(div);
      }
    }
  }

  _getStyles() {
    return `
      :host {
        display: block;
        font-family: var(--font-sans, "Inter", sans-serif);
        font-size: 0.8rem;
        padding: 0;
        color: #c0c0d0;
      }

      .dc-container {
        padding: 12px;
      }

      /* --- Idle State --- */
      .idle-state {
        text-align: center;
        padding: 24px 12px;
      }

      .idle-icon {
        font-size: 2rem;
        color: #334;
        margin-bottom: 8px;
      }

      .idle-text {
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        color: #556;
        margin-bottom: 4px;
      }

      .idle-subtext {
        font-size: 0.7rem;
        color: #445;
      }

      .idle-damaged {
        margin-top: 12px;
        font-size: 0.75rem;
        color: #ffaa00;
        font-weight: 600;
        letter-spacing: 0.05em;
      }

      .manual-start-btn {
        margin-top: 12px;
        padding: 8px 20px;
        background: #112244;
        border: 1px solid #4488ff;
        border-radius: 4px;
        color: #4488ff;
        font-family: var(--font-sans, "Inter", sans-serif);
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        cursor: pointer;
        transition: all 0.15s ease;
      }

      .manual-start-btn:hover {
        background: #1a3366;
        box-shadow: 0 0 10px rgba(68, 136, 255, 0.3);
      }

      /* --- Puzzle Header --- */
      .puzzle-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }

      .puzzle-title {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #889;
      }

      .puzzle-title strong {
        color: #ff6644;
      }

      .puzzle-status {
        font-size: 0.7rem;
        letter-spacing: 0.08em;
        color: #556;
        transition: color 0.2s ease;
      }

      .puzzle-status.success {
        color: #00ff88;
        font-weight: 700;
        text-shadow: 0 0 8px rgba(0, 255, 136, 0.4);
      }

      .puzzle-status.failure {
        color: #ff4444;
        font-weight: 700;
        text-shadow: 0 0 8px rgba(255, 68, 68, 0.4);
      }

      /* --- Timer Bar --- */
      .timer-bar {
        position: relative;
        height: 6px;
        background: #0a0a14;
        border: 1px solid #1a1a2e;
        border-radius: 3px;
        overflow: hidden;
        margin-bottom: 10px;
      }

      .timer-fill {
        height: 100%;
        background: linear-gradient(90deg, #00cc44, #44ee88);
        border-radius: 2px;
        transition: width 1s linear;
      }

      .timer-fill.urgent {
        animation: timer-pulse 0.5s ease-in-out infinite alternate;
      }

      @keyframes timer-pulse {
        from { opacity: 0.7; }
        to { opacity: 1; }
      }

      .timer-label {
        position: absolute;
        right: 6px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 0.6rem;
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: #aab;
        text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
      }

      /* --- Puzzle Grid --- */
      .puzzle-grid {
        display: grid;
        gap: 2px;
        aspect-ratio: auto;
        margin-bottom: 8px;
      }

      .grid-cell {
        background: #0a0a14;
        border: 1px solid #1a1a2e;
        border-radius: 2px;
        aspect-ratio: 1;
        cursor: pointer;
        position: relative;
        transition: border-color 0.15s ease, background 0.15s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 40px;
      }

      .grid-cell:hover:not(.blocked):not(.source):not(.target) {
        border-color: #4488ff;
        background: rgba(68, 136, 255, 0.05);
      }

      .grid-cell.blocked {
        background: #06060c;
        cursor: not-allowed;
        border-color: #151520;
      }

      .grid-cell.connected {
        border-color: rgba(0, 255, 136, 0.3);
        background: rgba(0, 255, 136, 0.03);
      }

      /* Source node: green */
      .grid-cell.source {
        border-color: #00cc44;
        background: rgba(0, 204, 68, 0.08);
        cursor: default;
      }

      /* Target node: red, pulsing */
      .grid-cell.target {
        border-color: #ff4444;
        background: rgba(255, 68, 68, 0.08);
        cursor: default;
        animation: target-pulse 1.5s ease-in-out infinite;
      }

      @keyframes target-pulse {
        0%, 100% { box-shadow: inset 0 0 8px rgba(255, 68, 68, 0.1); }
        50% { box-shadow: inset 0 0 16px rgba(255, 68, 68, 0.25); }
      }

      .node-label {
        position: absolute;
        top: 2px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 0.5rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: #00cc44;
        text-shadow: 0 0 4px rgba(0, 204, 68, 0.5);
        z-index: 2;
        pointer-events: none;
        white-space: nowrap;
      }

      .node-label.target-label {
        color: #ff6644;
        text-shadow: 0 0 4px rgba(255, 102, 68, 0.5);
      }

      /* --- Solved glow animation --- */
      .puzzle-grid.solved-glow .grid-cell.connected,
      .puzzle-grid.solved-glow .grid-cell.source,
      .puzzle-grid.solved-glow .grid-cell.target {
        border-color: #00ff88;
        background: rgba(0, 255, 136, 0.08);
        box-shadow: 0 0 12px rgba(0, 255, 136, 0.15);
        transition: all 0.3s ease;
      }

      .puzzle-grid.solved-glow .grid-cell.target {
        animation: none;
        border-color: #00ff88;
      }

      /* Flow animation on connected pipes when solved */
      .puzzle-grid.solved-glow .grid-cell.connected svg line,
      .puzzle-grid.solved-glow .grid-cell.source svg line,
      .puzzle-grid.solved-glow .grid-cell.target svg line {
        stroke-dasharray: 4 4;
        animation: flow-dash 0.6s linear infinite;
      }

      @keyframes flow-dash {
        from { stroke-dashoffset: 8; }
        to { stroke-dashoffset: 0; }
      }

      /* --- Failure flash --- */
      .puzzle-grid.failure-flash .grid-cell {
        border-color: rgba(255, 68, 68, 0.4);
        background: rgba(255, 0, 0, 0.06);
        transition: all 0.2s ease;
      }

      /* --- Legend --- */
      .puzzle-legend {
        display: flex;
        gap: 14px;
        align-items: center;
        font-size: 0.65rem;
        color: #556;
      }

      .legend-item {
        display: flex;
        align-items: center;
        gap: 4px;
        font-weight: 600;
        letter-spacing: 0.08em;
      }

      .legend-color {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }

      .legend-color.source {
        background: #00cc44;
        box-shadow: 0 0 4px rgba(0, 204, 68, 0.5);
      }

      .legend-color.target {
        background: #ff4444;
        box-shadow: 0 0 4px rgba(255, 68, 68, 0.5);
      }

      .legend-hint {
        margin-left: auto;
        font-size: 0.6rem;
        color: #445;
        font-style: italic;
      }

      /* --- Reduced motion --- */
      @media (prefers-reduced-motion: reduce) {
        .grid-cell.target { animation: none; }
        .timer-fill.urgent { animation: none; }
        .puzzle-grid.solved-glow .grid-cell.connected svg line,
        .puzzle-grid.solved-glow .grid-cell.source svg line,
        .puzzle-grid.solved-glow .grid-cell.target svg line {
          animation: none;
        }
      }
    `;
  }
}

customElements.define("damage-control-game", DamageControlGame);
