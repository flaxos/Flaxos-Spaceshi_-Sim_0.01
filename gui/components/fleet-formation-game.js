/**
 * Fleet Formation Game (ARCADE tier)
 *
 * Drag fleet ship icons into formation positions on a tactical grid.
 * Puzzle-like satisfaction: scattered ships organize into clean military
 * formations via drag-and-drop.
 *
 * State reads:
 *   fleet state from stateManager — fleet ship list, current formation type
 *   Falls back to mock ships if no fleet data available
 *
 * On formation complete: sends fleet_form command.
 */

import { wsClient } from "../js/ws-client.js";
import { stateManager } from "../js/state-manager.js";

// Formation templates (positions as fractions of grid, relative to center)
// Each position is [x, y] where 0,0 is center
const FORMATIONS = {
  LINE: {
    label: "LINE",
    positions: [
      [0, -0.3], [0, -0.1], [0, 0.1], [0, 0.3],
    ],
  },
  WEDGE: {
    label: "WEDGE",
    positions: [
      [0, -0.25], [-0.15, 0.0], [0.15, 0.0], [0, 0.25],
    ],
  },
  ECHELON: {
    label: "ECHELON",
    positions: [
      [-0.2, -0.25], [-0.1, -0.08], [0.1, 0.08], [0.2, 0.25],
    ],
  },
  DIAMOND: {
    label: "DIAMOND",
    positions: [
      [0, -0.3], [-0.25, 0], [0.25, 0], [0, 0.3],
    ],
  },
};

const SNAP_DISTANCE = 30;       // pixels to snap into a slot
const SHIP_COLORS = ["#4488ff", "#44cc88", "#ff8844", "#cc44cc", "#cccc44", "#44cccc"];

// Mock fleet ships when no fleet data available
const MOCK_SHIPS = [
  { id: "escort_1", name: "UNS Valor", classification: "corvette" },
  { id: "escort_2", name: "UNS Swift", classification: "frigate" },
  { id: "escort_3", name: "UNS Shield", classification: "corvette" },
  { id: "escort_4", name: "UNS Lance", classification: "destroyer" },
];

class FleetFormationGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._animFrame = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Game state
    this._selectedFormation = "WEDGE";
    this._fleetShips = [];           // [{id, name, color, placed, slotIndex}]
    this._slots = [];                // [{x, y, occupied, shipIndex}] — computed from formation
    this._formationComplete = false;
    this._completeSent = false;

    // Canvas interaction
    this._canvas = null;
    this._ctx = null;
    this._draggingShipIndex = null;
    this._dragOffsetX = 0;
    this._dragOffsetY = 0;

    // Ship positions on canvas (pixel coords)
    this._shipPositions = [];        // [{x, y}] parallel to _fleetShips
    this._stagingX = 0;              // left edge of staging area
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.querySelector(".formation-canvas");
    this._ctx = this._canvas?.getContext("2d");
    this._subscribe();
    this._setupInteraction();
    this._initGame();
    this._startLoop();

    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
    };
    document.addEventListener("tier-change", this._tierHandler);
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsub = stateManager.subscribe("*", () => {
      this._readState();
    });
  }

  /** Read fleet state from server telemetry */
  _readState() {
    const ship = stateManager.getShipState();
    if (!ship) return;

    const fleet = ship?.fleet || {};
    const fleetShips = fleet?.ships || fleet?.roster || [];

    // Only update ship list if we haven't started playing yet, or ships changed
    if (fleetShips.length > 0 && !this._formationComplete) {
      const ids = fleetShips.map(s => s.id || s.ship_id).join(",");
      const currentIds = this._fleetShips.map(s => s.id).join(",");
      if (ids !== currentIds) {
        this._fleetShips = fleetShips.slice(0, 6).map((s, i) => ({
          id: s.id || s.ship_id,
          name: s.name || s.designation || `Ship ${i + 1}`,
          color: SHIP_COLORS[i % SHIP_COLORS.length],
          placed: false,
          slotIndex: -1,
        }));
        this._resetPositions();
      }
    }
  }

  /** Initialize game with mock ships if no fleet data */
  _initGame() {
    if (this._fleetShips.length === 0) {
      this._fleetShips = MOCK_SHIPS.map((s, i) => ({
        id: s.id,
        name: s.name,
        color: SHIP_COLORS[i % SHIP_COLORS.length],
        placed: false,
        slotIndex: -1,
      }));
    }
    this._resetPositions();
    this._computeSlots();
  }

  /** Reset ship positions to staging area */
  _resetPositions() {
    const canvas = this._canvas;
    if (!canvas) return;

    this._stagingX = 30;
    this._shipPositions = this._fleetShips.map((_, i) => ({
      x: this._stagingX,
      y: 40 + i * 45,
    }));
    this._fleetShips.forEach(s => {
      s.placed = false;
      s.slotIndex = -1;
    });
    this._formationComplete = false;
    this._completeSent = false;

    // Clear slot occupancy
    this._slots.forEach(s => {
      s.occupied = false;
      s.shipIndex = -1;
    });
  }

  /** Compute slot positions from selected formation */
  _computeSlots() {
    const canvas = this._canvas;
    if (!canvas) return;

    const formation = FORMATIONS[this._selectedFormation];
    if (!formation) return;

    // Grid center (offset right to leave room for staging area)
    const cx = canvas.width * 0.6;
    const cy = canvas.height / 2;
    const gridScale = Math.min(canvas.width * 0.35, canvas.height * 0.4);

    // Use as many slots as we have ships (up to template length)
    const count = Math.min(this._fleetShips.length, formation.positions.length);
    this._slots = [];
    for (let i = 0; i < count; i++) {
      const [fx, fy] = formation.positions[i];
      this._slots.push({
        x: cx + fx * gridScale,
        y: cy + fy * gridScale,
        occupied: false,
        shipIndex: -1,
      });
    }

    // Un-place all ships when formation changes
    this._resetPositions();
  }

  /** Check if all slots are filled */
  _checkComplete() {
    const allPlaced = this._slots.length > 0 && this._slots.every(s => s.occupied);
    if (allPlaced && !this._formationComplete) {
      this._formationComplete = true;
    }

    // Send command on completion
    if (this._formationComplete && !this._completeSent) {
      const shipPositions = {};
      this._fleetShips.forEach((ship, i) => {
        if (ship.placed && ship.slotIndex >= 0) {
          shipPositions[ship.id] = ship.slotIndex;
        }
      });

      wsClient.sendShipCommand("fleet_form", {
        formation: this._selectedFormation.toLowerCase(),
        ship_positions: shipPositions,
      });
      this._completeSent = true;
    }
  }

  /** Main animation loop */
  _startLoop() {
    const loop = (timestamp) => {
      this._animFrame = requestAnimationFrame(loop);
      this._draw(timestamp);
    };
    this._animFrame = requestAnimationFrame(loop);
  }

  /** Draw the tactical grid, slots, and ships */
  _draw(timestamp) {
    const canvas = this._canvas;
    const ctx = this._ctx;
    if (!canvas || !ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    // Clear
    ctx.fillStyle = "#080812";
    ctx.fillRect(0, 0, w, h);

    // Draw grid lines
    this._drawGrid(ctx, w, h);

    // Draw staging area divider
    ctx.strokeStyle = "rgba(60, 60, 80, 0.3)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(80, 0);
    ctx.lineTo(80, h);
    ctx.stroke();
    ctx.setLineDash([]);

    // Staging area label
    ctx.fillStyle = "#334";
    ctx.font = "9px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("FLEET", 40, 16);

    // Draw formation slots (ghost positions)
    this._drawSlots(ctx, timestamp);

    // Draw flagship at center
    const cx = w * 0.6;
    const cy = h / 2;
    this._drawFlagship(ctx, cx, cy);

    // Draw fleet ships
    this._drawShips(ctx, timestamp);

    // Formation complete banner
    if (this._formationComplete) {
      this._drawCompleteBanner(ctx, w, h, timestamp);
    }
  }

  /** Draw subtle grid lines */
  _drawGrid(ctx, w, h) {
    ctx.strokeStyle = "rgba(40, 40, 60, 0.15)";
    ctx.lineWidth = 1;

    // Vertical lines
    for (let x = 80; x < w; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    // Horizontal lines
    for (let y = 0; y < h; y += 40) {
      ctx.beginPath();
      ctx.moveTo(80, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
  }

  /** Draw formation slot ghost positions */
  _drawSlots(ctx, timestamp) {
    const pulse = Math.sin(timestamp * 0.003) * 0.3 + 0.7;

    this._slots.forEach((slot, i) => {
      if (slot.occupied) {
        // Filled slot: subtle green ring
        ctx.strokeStyle = `rgba(68, 255, 136, 0.3)`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(slot.x, slot.y, 16, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        // Empty slot: dashed circle with pulse
        ctx.strokeStyle = `rgba(100, 120, 160, ${0.2 + 0.15 * pulse})`;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.arc(slot.x, slot.y, 16, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);

        // Slot number
        ctx.fillStyle = `rgba(100, 120, 160, ${0.3 + 0.1 * pulse})`;
        ctx.font = "9px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${i + 1}`, slot.x, slot.y);
      }
    });
  }

  /** Draw the flagship marker at grid center */
  _drawFlagship(ctx, x, y) {
    // White diamond
    ctx.fillStyle = "#dde";
    ctx.beginPath();
    ctx.moveTo(x, y - 8);
    ctx.lineTo(x + 6, y);
    ctx.lineTo(x, y + 8);
    ctx.lineTo(x - 6, y);
    ctx.closePath();
    ctx.fill();

    // Label
    ctx.fillStyle = "#99a";
    ctx.font = "bold 8px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText("FLAG", x, y + 12);
  }

  /** Draw fleet ship icons (triangles/chevrons) */
  _drawShips(ctx, timestamp) {
    this._fleetShips.forEach((ship, i) => {
      const pos = this._shipPositions[i];
      if (!pos) return;

      const isBeingDragged = this._draggingShipIndex === i;
      const size = isBeingDragged ? 14 : 12;

      // Ship chevron
      ctx.fillStyle = ship.color;
      if (ship.placed) {
        // Placed ship: glow
        ctx.shadowColor = ship.color;
        ctx.shadowBlur = 8;
      }
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y - size);
      ctx.lineTo(pos.x + size * 0.7, pos.y + size * 0.5);
      ctx.lineTo(pos.x, pos.y + size * 0.2);
      ctx.lineTo(pos.x - size * 0.7, pos.y + size * 0.5);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;

      // Ship name label (only in staging area or when placed)
      if (!isBeingDragged) {
        ctx.fillStyle = ship.placed ? ship.color : "#667";
        ctx.font = "8px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const label = ship.name.length > 10 ? ship.name.substring(0, 10) : ship.name;
        ctx.fillText(label, pos.x, pos.y + size + 4);
      }
    });
  }

  /** Draw formation complete banner */
  _drawCompleteBanner(ctx, w, h, timestamp) {
    const alpha = Math.sin(timestamp * 0.004) * 0.15 + 0.85;

    ctx.fillStyle = `rgba(0, 40, 20, 0.6)`;
    ctx.fillRect(w * 0.25, h - 30, w * 0.5, 24);

    ctx.strokeStyle = `rgba(68, 255, 136, ${alpha})`;
    ctx.lineWidth = 1;
    ctx.strokeRect(w * 0.25, h - 30, w * 0.5, 24);

    ctx.fillStyle = `rgba(68, 255, 136, ${alpha})`;
    ctx.font = "bold 11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("FORMATION SET", w / 2, h - 18);
  }

  /** Set up mouse/touch interaction for ship dragging */
  _setupInteraction() {
    const canvas = this._canvas;
    if (!canvas) return;

    const getCanvasCoords = (clientX, clientY) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      return {
        x: (clientX - rect.left) * scaleX,
        y: (clientY - rect.top) * scaleY,
      };
    };

    const findShipAt = (cx, cy) => {
      // Check in reverse order (topmost first)
      for (let i = this._fleetShips.length - 1; i >= 0; i--) {
        const pos = this._shipPositions[i];
        if (!pos) continue;
        const dx = cx - pos.x;
        const dy = cy - pos.y;
        if (dx * dx + dy * dy < 20 * 20) return i;
      }
      return -1;
    };

    const startDrag = (clientX, clientY) => {
      const { x, y } = getCanvasCoords(clientX, clientY);
      const shipIdx = findShipAt(x, y);
      if (shipIdx < 0) return;

      this._draggingShipIndex = shipIdx;
      this._dragOffsetX = x - this._shipPositions[shipIdx].x;
      this._dragOffsetY = y - this._shipPositions[shipIdx].y;

      // Un-place if already placed
      const ship = this._fleetShips[shipIdx];
      if (ship.placed && ship.slotIndex >= 0) {
        this._slots[ship.slotIndex].occupied = false;
        this._slots[ship.slotIndex].shipIndex = -1;
        ship.placed = false;
        ship.slotIndex = -1;
        this._formationComplete = false;
        this._completeSent = false;
      }
    };

    const moveDrag = (clientX, clientY) => {
      if (this._draggingShipIndex === null) return;
      const { x, y } = getCanvasCoords(clientX, clientY);
      this._shipPositions[this._draggingShipIndex] = {
        x: x - this._dragOffsetX,
        y: y - this._dragOffsetY,
      };
    };

    const endDrag = () => {
      if (this._draggingShipIndex === null) return;
      const shipIdx = this._draggingShipIndex;
      const pos = this._shipPositions[shipIdx];
      this._draggingShipIndex = null;

      // Check if near any unoccupied slot
      let snapped = false;
      for (let i = 0; i < this._slots.length; i++) {
        const slot = this._slots[i];
        if (slot.occupied) continue;
        const dx = pos.x - slot.x;
        const dy = pos.y - slot.y;
        if (dx * dx + dy * dy < SNAP_DISTANCE * SNAP_DISTANCE) {
          // Snap into slot
          this._shipPositions[shipIdx] = { x: slot.x, y: slot.y };
          slot.occupied = true;
          slot.shipIndex = shipIdx;
          this._fleetShips[shipIdx].placed = true;
          this._fleetShips[shipIdx].slotIndex = i;
          snapped = true;
          break;
        }
      }

      // If not snapped, return to staging area
      if (!snapped) {
        this._shipPositions[shipIdx] = {
          x: this._stagingX,
          y: 40 + shipIdx * 45,
        };
        this._fleetShips[shipIdx].placed = false;
        this._fleetShips[shipIdx].slotIndex = -1;
      }

      this._checkComplete();
    };

    // Mouse
    canvas.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startDrag(e.clientX, e.clientY);
    });
    canvas.addEventListener("mousemove", (e) => moveDrag(e.clientX, e.clientY));
    canvas.addEventListener("mouseup", () => endDrag());
    canvas.addEventListener("mouseleave", () => endDrag());

    // Touch
    canvas.addEventListener("touchstart", (e) => {
      e.preventDefault();
      const t = e.touches[0];
      startDrag(t.clientX, t.clientY);
    });
    canvas.addEventListener("touchmove", (e) => {
      e.preventDefault();
      const t = e.touches[0];
      moveDrag(t.clientX, t.clientY);
    });
    canvas.addEventListener("touchend", () => endDrag());
    canvas.addEventListener("touchcancel", () => endDrag());

    // Formation type tabs
    this.shadowRoot.querySelectorAll(".formation-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        this._selectedFormation = tab.dataset.formation;
        // Update active tab styling
        this.shadowRoot.querySelectorAll(".formation-tab").forEach(t =>
          t.classList.toggle("active", t === tab)
        );
        this._computeSlots();
      });
    });

    // Reset button
    const resetBtn = this.shadowRoot.querySelector(".reset-btn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => this._resetPositions());
    }
  }

  _render() {
    const formationTabs = Object.keys(FORMATIONS).map(key => {
      const active = key === this._selectedFormation ? "active" : "";
      return `<button class="formation-tab ${active}" data-formation="${key}">${FORMATIONS[key].label}</button>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-sans, "Inter", sans-serif);
          font-size: 0.8rem;
          padding: 0;
        }

        .formation-game-root {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 12px;
        }

        /* --- Formation type tabs --- */
        .formation-tabs {
          display: flex;
          gap: 4px;
        }

        .formation-tab {
          flex: 1;
          padding: 5px 8px;
          font-size: 0.65rem;
          font-weight: 600;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          background: #0a0a14;
          color: #556;
          cursor: pointer;
          transition: all 0.15s ease;
          font-family: inherit;
        }

        .formation-tab:hover {
          background: #12121e;
          border-color: #2a2a3e;
          color: #88a;
        }

        .formation-tab.active {
          background: #111128;
          border-color: #4488ff;
          color: #4488ff;
          box-shadow: 0 0 6px rgba(68, 136, 255, 0.2);
        }

        /* --- Canvas --- */
        .formation-canvas {
          width: 100%;
          height: 250px;
          border: 1px solid #1a1a2e;
          border-radius: 3px;
          display: block;
          cursor: grab;
          touch-action: none;
        }

        .formation-canvas:active {
          cursor: grabbing;
        }

        /* --- Controls row --- */
        .controls-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .ship-count {
          font-size: 0.7rem;
          color: #667;
          letter-spacing: 0.08em;
        }

        .ship-count .placed {
          color: #4c8;
          font-weight: 600;
        }

        .reset-btn {
          padding: 4px 12px;
          font-size: 0.65rem;
          font-weight: 600;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          border: 1px solid #2a2a3e;
          border-radius: 3px;
          background: #0e0e18;
          color: #667;
          cursor: pointer;
          transition: all 0.15s ease;
          font-family: inherit;
        }

        .reset-btn:hover {
          background: #16162a;
          border-color: #3a3a4e;
          color: #99a;
        }

        /* --- Hint text --- */
        .hint {
          text-align: center;
          font-size: 0.6rem;
          color: #445;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
      </style>

      <div class="formation-game-root">
        <!-- Formation type selector -->
        <div class="formation-tabs">
          ${formationTabs}
        </div>

        <!-- Tactical grid canvas -->
        <canvas class="formation-canvas" width="400" height="250"></canvas>

        <!-- Controls row -->
        <div class="controls-row">
          <span class="ship-count">
            <span class="placed">0</span> / 0 placed
          </span>
          <button class="reset-btn">RESET</button>
        </div>

        <div class="hint">drag ships from staging area into formation slots</div>
      </div>
    `;
  }
}

customElements.define("fleet-formation-game", FleetFormationGame);
