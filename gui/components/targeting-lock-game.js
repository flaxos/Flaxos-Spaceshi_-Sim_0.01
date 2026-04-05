/**
 * Targeting Lock Game — ARCADE Tier Interactive Lock Minigame
 *
 * Instead of passively waiting for lock progress, ARCADE tier players
 * actively track a moving reticle to maintain lock quality. Better tracking
 * means faster lock acquisition and higher solution confidence.
 *
 * The game does NOT replace the server's targeting system. It sends periodic
 * lock_target commands when the player is tracking well, and reads actual
 * lock_progress from stateManager. The tracking score is purely local UX.
 *
 * Visibility rules:
 *   - ARCADE tier only
 *   - Target designated but NOT yet locked
 *   - Hidden when no target or already locked
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";

const CANVAS_W = 200;
const CANVAS_H = 200;
const RETICLE_RADIUS = 8;
const CURSOR_RADIUS = 15;
const MAX_TRACK_DIST = 60; // px — beyond this, tracking score is 0
const DIR_CHANGE_MIN = 1000; // ms
const DIR_CHANGE_MAX = 3000; // ms
const LOCK_CMD_INTERVAL = 800; // ms — how often to send lock_target while tracking well

class TargetingLockGame extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    // Target reticle position & velocity
    this._targetX = CANVAS_W / 2;
    this._targetY = CANVAS_H / 2;
    this._targetVelX = 0;
    this._targetVelY = 0;

    // Player cursor position
    this._cursorX = CANVAS_W / 2;
    this._cursorY = CANVAS_H / 2;

    // Game state
    this._trackingScore = 0;
    this._gameActive = false;
    this._animFrame = null;
    this._lastFrameTime = 0;
    this._dirChangeTimer = 0;
    this._nextDirChange = 2000;
    this._lastLockCmd = 0;

    // Success flash
    this._successFlash = 0;

    // Subscriptions
    this._unsubscribe = null;
    this._tierHandler = null;
    this._tier = window.controlTier || "arcade";

    // Canvas ref
    this._canvas = null;
    this._ctx = null;

    // Bound handlers for cleanup
    this._boundMouseMove = this._onMouseMove.bind(this);
    this._boundTouchMove = this._onTouchMove.bind(this);
    this._boundFrame = this._frame.bind(this);
  }

  connectedCallback() {
    this._render();
    this._canvas = this.shadowRoot.getElementById("lock-canvas");
    this._ctx = this._canvas.getContext("2d");

    // Mouse/touch input on canvas
    this._canvas.addEventListener("mousemove", this._boundMouseMove);
    this._canvas.addEventListener("touchmove", this._boundTouchMove, { passive: false });

    // State subscription
    this._unsubscribe = stateManager.subscribe("*", () => this._onStateUpdate());

    // Tier change listener
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._onStateUpdate();
    };
    document.addEventListener("tier-change", this._tierHandler);

    // Initial state check
    this._onStateUpdate();
  }

  disconnectedCallback() {
    // Cancel animation
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }

    // Remove event listeners
    if (this._canvas) {
      this._canvas.removeEventListener("mousemove", this._boundMouseMove);
      this._canvas.removeEventListener("touchmove", this._boundTouchMove);
    }

    // Unsubscribe state
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }

    // Remove tier listener
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  // --- Input Handlers ---

  _onMouseMove(e) {
    const rect = this._canvas.getBoundingClientRect();
    this._cursorX = Math.max(0, Math.min(CANVAS_W, (e.clientX - rect.left) * (CANVAS_W / rect.width)));
    this._cursorY = Math.max(0, Math.min(CANVAS_H, (e.clientY - rect.top) * (CANVAS_H / rect.height)));
  }

  _onTouchMove(e) {
    e.preventDefault();
    const touch = e.touches[0];
    if (!touch) return;
    const rect = this._canvas.getBoundingClientRect();
    this._cursorX = Math.max(0, Math.min(CANVAS_W, (touch.clientX - rect.left) * (CANVAS_W / rect.width)));
    this._cursorY = Math.max(0, Math.min(CANVAS_H, (touch.clientY - rect.top) * (CANVAS_H / rect.height)));
  }

  // --- State Management ---

  _onStateUpdate() {
    const targeting = stateManager.getTargeting();
    const lockState = targeting?.lock_state || "none";
    const hasTarget = !!(targeting?.locked_target || targeting?.designated_target || targeting?.target_id);
    const isArcade = this._tier === "arcade";

    // Game is active when: arcade tier, target designated, not yet locked
    const shouldBeActive = isArcade && hasTarget && lockState !== "locked" && lockState !== "none";

    if (shouldBeActive && !this._gameActive) {
      this._startGame(targeting);
    } else if (!shouldBeActive && this._gameActive) {
      // If we just got locked, show success flash before stopping
      if (lockState === "locked") {
        this._successFlash = 1.0;
        // Let the flash play out, then stop after 1.5s
        setTimeout(() => this._stopGame(), 1500);
      } else {
        this._stopGame();
      }
    }

    // Update host visibility
    const shouldShow = isArcade && hasTarget && (lockState !== "none");
    this.style.display = shouldShow ? "block" : "none";
  }

  _startGame(targeting) {
    this._gameActive = true;
    this._targetX = CANVAS_W / 2;
    this._targetY = CANVAS_H / 2;
    this._cursorX = CANVAS_W / 2;
    this._cursorY = CANVAS_H / 2;
    this._trackingScore = 0;
    this._successFlash = 0;
    this._lastFrameTime = performance.now();
    this._dirChangeTimer = 0;
    this._pickNewDirection(targeting);
    this._animFrame = requestAnimationFrame(this._boundFrame);
  }

  _stopGame() {
    this._gameActive = false;
    if (this._animFrame) {
      cancelAnimationFrame(this._animFrame);
      this._animFrame = null;
    }
  }

  // --- Game Loop ---

  _frame(timestamp) {
    if (!this._gameActive && this._successFlash <= 0) return;

    const dt = Math.min((timestamp - this._lastFrameTime) / 1000, 0.1); // cap at 100ms
    this._lastFrameTime = timestamp;

    const targeting = stateManager.getTargeting();

    if (this._gameActive) {
      // 1. Update direction change timer
      this._dirChangeTimer += dt * 1000;
      if (this._dirChangeTimer >= this._nextDirChange) {
        this._pickNewDirection(targeting);
        this._dirChangeTimer = 0;
        this._nextDirChange = DIR_CHANGE_MIN + Math.random() * (DIR_CHANGE_MAX - DIR_CHANGE_MIN);
      }

      // 2. Move target reticle
      this._targetX += this._targetVelX * dt;
      this._targetY += this._targetVelY * dt;

      // Add jitter based on range (further = more jitter)
      const range = targeting?.range || targeting?.target_range || 10000;
      const jitterScale = Math.min(2.0, range / 50000); // 0-2px jitter
      this._targetX += (Math.random() - 0.5) * jitterScale;
      this._targetY += (Math.random() - 0.5) * jitterScale;

      // Bounce off edges with padding
      const pad = RETICLE_RADIUS + 10;
      if (this._targetX < pad) { this._targetX = pad; this._targetVelX = Math.abs(this._targetVelX); }
      if (this._targetX > CANVAS_W - pad) { this._targetX = CANVAS_W - pad; this._targetVelX = -Math.abs(this._targetVelX); }
      if (this._targetY < pad) { this._targetY = pad; this._targetVelY = Math.abs(this._targetVelY); }
      if (this._targetY > CANVAS_H - pad) { this._targetY = CANVAS_H - pad; this._targetVelY = -Math.abs(this._targetVelY); }

      // 3. Calculate tracking score
      const dx = this._cursorX - this._targetX;
      const dy = this._cursorY - this._targetY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      this._trackingScore = Math.max(0, 1.0 - dist / MAX_TRACK_DIST);

      // 4. Send lock_target periodically if tracking well
      if (this._trackingScore > 0.5 && timestamp - this._lastLockCmd > LOCK_CMD_INTERVAL) {
        this._lastLockCmd = timestamp;
        const targetId = targeting?.locked_target || targeting?.designated_target || targeting?.target_id;
        if (targetId) {
          wsClient.sendShipCommand("lock_target", { target: targetId }).catch(() => {
            // Silently ignore — lock commands are best-effort
          });
        }
      }
    }

    // 5. Decay success flash
    if (this._successFlash > 0) {
      this._successFlash = Math.max(0, this._successFlash - dt * 1.5);
    }

    // 6. Read lock progress from server state
    const lockProgress = targeting?.lock_progress ?? 0;
    const lockState = targeting?.lock_state || "none";

    // 7. Draw
    this._draw(lockProgress, lockState);

    // Continue loop
    this._animFrame = requestAnimationFrame(this._boundFrame);
  }

  _pickNewDirection(targeting) {
    // Speed scales with target acceleration magnitude
    const accelMag = targeting?.target_accel_magnitude ?? 10;
    // Base speed 20-60 px/s, scaled by accel (higher accel = faster reticle)
    const speed = 20 + Math.min(40, accelMag / 3);

    const angle = Math.random() * Math.PI * 2;
    this._targetVelX = Math.cos(angle) * speed;
    this._targetVelY = Math.sin(angle) * speed;
  }

  // --- Drawing ---

  _draw(lockProgress, lockState) {
    const ctx = this._ctx;
    if (!ctx) return;

    const w = CANVAS_W;
    const h = CANVAS_H;

    // Clear
    ctx.fillStyle = "#0a0a14";
    ctx.fillRect(0, 0, w, h);

    // Subtle grid
    ctx.strokeStyle = "#1a1a2a";
    ctx.lineWidth = 0.5;
    const gridStep = 20;
    for (let x = gridStep; x < w; x += gridStep) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = gridStep; y < h; y += gridStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    // Center crosshair (very faint)
    ctx.strokeStyle = "#1a1a2a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(w / 2, 0);
    ctx.lineTo(w / 2, h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    if (this._gameActive) {
      // Target reticle — amber/orange crosshair + circle
      this._drawReticle(ctx);

      // Player cursor ring — color based on tracking score
      this._drawCursor(ctx);

      // Tracking score indicator (top-left)
      this._drawTrackingScore(ctx);
    }

    // Lock progress bar (bottom of canvas)
    this._drawProgressBar(ctx, lockProgress, lockState);

    // Success flash overlay
    if (this._successFlash > 0) {
      this._drawSuccessFlash(ctx);
    }
  }

  _drawReticle(ctx) {
    const x = this._targetX;
    const y = this._targetY;
    const r = RETICLE_RADIUS;

    // Color ring based on cursor proximity
    const dx = this._cursorX - x;
    const dy = this._cursorY - y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    let ringColor;
    if (dist < MAX_TRACK_DIST * 0.3) {
      ringColor = "#00ff88"; // green — close
    } else if (dist < MAX_TRACK_DIST * 0.7) {
      ringColor = "#ffcc00"; // yellow — medium
    } else {
      ringColor = "#ff4444"; // red — far
    }

    // Outer glow ring
    ctx.strokeStyle = ringColor;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.3;
    ctx.beginPath();
    ctx.arc(x, y, r + 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1.0;

    // Main reticle circle
    ctx.strokeStyle = "#ff8800";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();

    // Crosshair lines
    const lineLen = r + 6;
    ctx.strokeStyle = "#ff8800";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x - lineLen, y);
    ctx.lineTo(x - r - 2, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + r + 2, y);
    ctx.lineTo(x + lineLen, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y - lineLen);
    ctx.lineTo(x, y - r - 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y + r + 2);
    ctx.lineTo(x, y + lineLen);
    ctx.stroke();

    // Center dot
    ctx.fillStyle = "#ff8800";
    ctx.beginPath();
    ctx.arc(x, y, 1.5, 0, Math.PI * 2);
    ctx.fill();
  }

  _drawCursor(ctx) {
    const x = this._cursorX;
    const y = this._cursorY;

    // Color based on tracking score
    let color;
    if (this._trackingScore > 0.7) {
      color = "#00ff88";
    } else if (this._trackingScore > 0.3) {
      color = "#ffcc00";
    } else {
      color = "#ff4444";
    }

    // Outer cursor ring
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.8;
    ctx.beginPath();
    ctx.arc(x, y, CURSOR_RADIUS, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1.0;

    // Inner dot
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.arc(x, y, 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1.0;
  }

  _drawTrackingScore(ctx) {
    const score = this._trackingScore;
    const label = `TRACK ${Math.round(score * 100)}%`;

    let color;
    if (score > 0.7) color = "#00ff88";
    else if (score > 0.3) color = "#ffcc00";
    else color = "#ff4444";

    ctx.font = "bold 10px 'JetBrains Mono', monospace";
    ctx.fillStyle = color;
    ctx.textAlign = "left";
    ctx.fillText(label, 6, 14);
  }

  _drawProgressBar(ctx, lockProgress, lockState) {
    const barY = CANVAS_H - 12;
    const barH = 8;
    const barPad = 4;
    const barW = CANVAS_W - barPad * 2;

    // Background
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(barPad, barY, barW, barH);

    // Border
    ctx.strokeStyle = "#2a2a3a";
    ctx.lineWidth = 1;
    ctx.strokeRect(barPad, barY, barW, barH);

    // Fill
    const fillW = barW * Math.max(0, Math.min(1, lockProgress));
    if (fillW > 0) {
      const fillColor = lockState === "locked" ? "#00ff88" : "#4488ff";
      ctx.fillStyle = fillColor;
      ctx.fillRect(barPad + 1, barY + 1, fillW - 2, barH - 2);
    }

    // Label
    ctx.font = "bold 7px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#8888aa";
    ctx.textAlign = "center";
    const pct = Math.round(lockProgress * 100);
    ctx.fillText(`LOCK ${pct}%`, CANVAS_W / 2, barY - 2);
  }

  _drawSuccessFlash(ctx) {
    // Green flash overlay that fades out
    ctx.fillStyle = `rgba(0, 255, 136, ${this._successFlash * 0.15})`;
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // "LOCK ACQUIRED" text
    if (this._successFlash > 0.3) {
      ctx.font = "bold 16px 'JetBrains Mono', monospace";
      ctx.fillStyle = `rgba(0, 255, 136, ${Math.min(1, this._successFlash * 2)})`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("LOCK ACQUIRED", CANVAS_W / 2, CANVAS_H / 2);
      ctx.textBaseline = "alphabetic";

      // Glow effect via shadow
      ctx.shadowColor = "#00ff88";
      ctx.shadowBlur = 20;
      ctx.fillText("LOCK ACQUIRED", CANVAS_W / 2, CANVAS_H / 2);
      ctx.shadowBlur = 0;
    }
  }

  // --- Render ---

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: none;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .lock-game-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          padding: 8px;
        }

        .game-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          font-size: 0.65rem;
          color: #6688cc;
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        .game-header .hint {
          color: #445577;
          font-style: italic;
          font-size: 0.6rem;
        }

        #lock-canvas {
          border: 1px solid #2a2a3a;
          border-radius: 4px;
          cursor: crosshair;
          width: 100%;
          max-width: ${CANVAS_W}px;
          aspect-ratio: 1 / 1;

          /* Prevent text selection on touch */
          touch-action: none;
          user-select: none;
          -webkit-user-select: none;
        }

        #lock-canvas:hover {
          border-color: #4488ff;
        }
      </style>

      <div class="lock-game-container">
        <div class="game-header">
          <span>ACTIVE TRACKING</span>
          <span class="hint">track the reticle</span>
        </div>
        <canvas id="lock-canvas" width="${CANVAS_W}" height="${CANVAS_H}"></canvas>
      </div>
    `;
  }
}

customElements.define("targeting-lock-game", TargetingLockGame);
