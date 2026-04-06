/**
 * Weapon Fire Controls
 * Tactical station fire control: railgun fire, PDC mode, torpedo launch,
 * target designation, and damage assessment.
 *
 * Uses commands: designate_target, request_solution, fire_railgun,
 * set_pdc_mode, launch_torpedo, launch_missile, assess_damage
 */

import { stateManager } from "../js/state-manager.js";
import { wsClient } from "../js/ws-client.js";
import { getProposalCSS } from "../js/proposal-styles.js";

class WeaponControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsubscribe = null;
    this._pdcMode = "auto";
    this._assessmentData = null;
    // Launcher type: "torpedo" or "missile" — determines which command is sent
    this._launcherType = "torpedo";

    // Missile salvo size (1, 2, 4, or "all" resolved at fire time)
    this._salvoSize = 1;
    // Missile flight profile sent with launch_missile command
    this._missileProfile = "direct";

    // Auto-execute authorization state per weapon type.
    // When authorized AND conditions are met (lock, solution, ammo, cooldown),
    // the weapon fires automatically on the next _updateDisplay tick.
    this._authorized = { railgun: false, torpedo: false, missile: false };
    // Tracks in-flight salvo to prevent re-fire during staggered launch
    this._salvoInProgress = false;
    this._tier = window.controlTier || "arcade";
  }

  connectedCallback() {
    this.render();
    this._subscribe();
    this._setupInteraction();

    this._contactSelectedHandler = (e) => {
      this._selectedContact = e.detail.contactId;
      this._updateDisplay();
    };
    document.addEventListener("contact-selected", this._contactSelectedHandler);

    // Tier-change listener: re-render weapon controls per tier
    this._tierHandler = (e) => {
      this._tier = e.detail?.tier || "arcade";
      this._applyTier();
    };
    document.addEventListener("tier-change", this._tierHandler);
    // Apply tier on first connect
    this._applyTier();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._contactSelectedHandler) {
      document.removeEventListener("contact-selected", this._contactSelectedHandler);
      this._contactSelectedHandler = null;
    }
    if (this._tierHandler) {
      document.removeEventListener("tier-change", this._tierHandler);
      this._tierHandler = null;
    }
  }

  _subscribe() {
    this._unsubscribe = stateManager.subscribe("*", () => {
      this._updateDisplay();
    });
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          font-family: var(--font-sans, "Inter", sans-serif);
        }

        .weapon-group {
          margin-bottom: 16px;
        }

        .weapon-group:last-child {
          margin-bottom: 0;
        }

        .group-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-secondary, #888899);
          margin-bottom: 8px;
        }

        /* Pulse animation for fire-ready buttons */
        @keyframes fire-ready-pulse {
          0%, 100% { box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3); }
          50% { box-shadow: 0 4px 20px rgba(255, 68, 68, 0.55), 0 0 8px rgba(255, 68, 68, 0.2); }
        }

        .fire-btn {
          width: 100%;
          padding: 14px 16px;
          border-radius: 8px;
          font-size: 1.1rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          cursor: pointer;
          min-height: 60px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: all 0.1s ease;
          font-family: inherit;
        }

        /* Disabled / not-ready state for all fire buttons */
        .fire-btn:disabled {
          background: var(--bg-input, #1a1a24);
          color: var(--text-dim, #555566);
          border: 2px solid var(--border-default, #2a2a3a);
          cursor: not-allowed;
          box-shadow: none;
          animation: none;
        }

        .railgun-btn {
          background: var(--status-critical, #ff4444);
          border: 2px solid var(--status-critical, #ff4444);
          color: white;
          box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
        }

        .railgun-btn:not(:disabled) {
          animation: fire-ready-pulse 2s ease-in-out infinite;
        }

        .railgun-btn:hover:not(:disabled) {
          filter: brightness(1.15);
          transform: translateY(-1px);
        }

        .railgun-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        .torpedo-btn {
          background: var(--status-critical, #ff4444);
          border: 2px solid var(--status-critical, #ff4444);
          color: white;
          box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
        }

        .torpedo-btn:not(:disabled) {
          animation: fire-ready-pulse 2s ease-in-out infinite;
        }

        .torpedo-btn:hover:not(:disabled) {
          filter: brightness(1.15);
          transform: translateY(-1px);
        }

        .torpedo-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        .torpedo-count {
          font-size: 0.75rem;
          opacity: 0.9;
        }

        /* Launcher Type Selector — styled like PDC mode toggle */
        .launcher-type-group {
          display: flex;
          gap: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 4px;
          margin-bottom: 8px;
        }

        .launcher-type-btn {
          flex: 1;
          padding: 8px 6px;
          border: 1px solid transparent;
          border-radius: 6px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 36px;
        }

        .launcher-type-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .launcher-type-btn.active {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.1);
        }

        .launcher-type-btn.active.missile {
          color: #ff8800;
          border-color: #ff8800;
          background: rgba(255, 136, 0, 0.1);
        }

        .launcher-type-label {
          display: flex;
          align-items: center;
          gap: 6px;
          justify-content: center;
        }

        .launcher-type-indicator {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
          flex-shrink: 0;
        }

        /* Missile fire button variant */
        .missile-btn {
          background: #ff8800;
          border: 2px solid #ff8800;
          color: white;
          box-shadow: 0 4px 12px rgba(255, 136, 0, 0.3);
        }

        .missile-btn:not(:disabled) {
          animation: fire-ready-pulse-missile 2s ease-in-out infinite;
        }

        .missile-btn:hover:not(:disabled) {
          filter: brightness(1.15);
          transform: translateY(-1px);
        }

        .missile-btn:active:not(:disabled) {
          transform: translateY(0);
        }

        @keyframes fire-ready-pulse-missile {
          0%, 100% { box-shadow: 0 4px 12px rgba(255, 136, 0, 0.3); }
          50% { box-shadow: 0 4px 20px rgba(255, 136, 0, 0.55), 0 0 8px rgba(255, 136, 0, 0.2); }
        }

        /* PDC Mode Selector */
        .pdc-mode-group {
          display: flex;
          gap: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 4px;
        }

        .pdc-mode-btn {
          flex: 1;
          padding: 8px 6px;
          border: 1px solid transparent;
          border-radius: 6px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 36px;
        }

        .pdc-mode-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .pdc-mode-btn.active {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.1);
        }

        .pdc-mode-btn.active.hold-fire {
          color: var(--status-warning, #ffaa00);
          border-color: var(--status-warning, #ffaa00);
          background: rgba(255, 170, 0, 0.1);
        }

        .pdc-mode-label {
          display: flex;
          align-items: center;
          gap: 6px;
          justify-content: center;
        }

        .pdc-indicator {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
          flex-shrink: 0;
        }

        /* Assess damage button */
        .assess-btn {
          width: 100%;
          padding: 10px 16px;
          background: rgba(0, 170, 255, 0.08);
          border: 1px solid var(--status-info, #00aaff);
          border-radius: 6px;
          color: var(--status-info, #00aaff);
          font-family: inherit;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          min-height: 40px;
          transition: background 0.15s ease;
        }

        .assess-btn:hover:not(:disabled) {
          background: rgba(0, 170, 255, 0.15);
        }

        .assess-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        /* Assessment results */
        .assessment-results {
          margin-top: 8px;
          padding: 10px 12px;
          background: rgba(0, 0, 0, 0.25);
          border-radius: 6px;
          border: 1px solid var(--border-default, #2a2a3a);
        }

        .assessment-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 3px 0;
          font-size: 0.75rem;
        }

        .assessment-label {
          color: var(--text-secondary, #888899);
          text-transform: uppercase;
          font-size: 0.65rem;
          letter-spacing: 0.3px;
        }

        .assessment-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
        }

        .assessment-value.nominal { color: var(--status-nominal, #00ff88); }
        .assessment-value.impaired { color: var(--status-warning, #ffaa00); }
        .assessment-value.critical { color: var(--status-critical, #ff4444); }
        .assessment-value.destroyed { color: var(--text-dim, #555566); text-decoration: line-through; }
        .assessment-value.unknown { color: var(--text-dim, #555566); }

        .assessment-confidence {
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          margin-top: 6px;
          padding-top: 6px;
          border-top: 1px solid var(--border-default, #2a2a3a);
        }

        /* --- Ammo/Heat HUD bar (above fire controls) --- */
        .ammo-heat-hud {
          padding: 8px 10px;
          margin-bottom: 14px;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
        }

        .ammo-summary {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 12px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          margin-bottom: 6px;
        }

        .ammo-item {
          display: flex;
          align-items: center;
          gap: 4px;
          white-space: nowrap;
        }

        .ammo-label {
          color: var(--text-secondary, #888899);
          font-weight: 600;
          font-size: 0.6rem;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .ammo-value {
          color: var(--text-primary, #e0e0e0);
        }

        .ammo-value.low {
          color: var(--status-warning, #ffaa00);
        }

        .ammo-value.critical {
          color: var(--status-critical, #ff4444);
        }

        .ammo-value.empty {
          color: var(--text-dim, #555566);
        }

        .ammo-separator {
          color: var(--text-dim, #555566);
          font-size: 0.55rem;
          user-select: none;
        }

        .heat-bar-section {
          margin-bottom: 4px;
        }

        .heat-bar-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 3px;
        }

        .heat-bar-label {
          font-size: 0.6rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          color: var(--text-secondary, #888899);
        }

        .heat-bar-value {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
        }

        .heat-bar-value.cool { color: var(--status-nominal, #00ff88); }
        .heat-bar-value.warm { color: var(--status-warning, #ffaa00); }
        .heat-bar-value.hot { color: var(--status-critical, #ff4444); }

        .heat-bar-container {
          height: 8px;
          background: var(--bg-input, #1a1a24);
          border-radius: 4px;
          overflow: hidden;
        }

        .heat-bar-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.3s ease, background 0.3s ease;
        }

        .heat-bar-fill.cool {
          background: var(--status-nominal, #00ff88);
        }

        .heat-bar-fill.warm {
          background: var(--status-warning, #ffaa00);
        }

        .heat-bar-fill.hot {
          background: linear-gradient(90deg, #ff4444, #ff6644);
        }

        .reload-status {
          margin-top: 6px;
          display: flex;
          flex-wrap: wrap;
          gap: 4px 10px;
          font-size: 0.65rem;
        }

        .reload-item {
          display: flex;
          align-items: center;
          gap: 4px;
          color: var(--status-warning, #ffaa00);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
        }

        .reload-indicator {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--status-warning, #ffaa00);
          animation: reload-blink 1s ease-in-out infinite;
        }

        @keyframes reload-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .cease-fire-btn {
          width: 100%;
          padding: 12px 16px;
          background: transparent;
          border: 2px solid var(--status-warning, #ffaa00);
          border-radius: 8px;
          color: var(--status-warning, #ffaa00);
          font-family: inherit;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          min-height: 44px;
          transition: all 0.1s ease;
        }

        .cease-fire-btn:hover {
          background: rgba(255, 170, 0, 0.1);
        }

        .fire-hint {
          margin-top: 6px;
          font-size: 0.7rem;
          color: var(--text-dim, #555566);
          text-align: center;
          font-style: italic;
          min-height: 1.2em;
        }

        .target-lock-row {
          margin-bottom: 12px;
        }

        .lock-btn {
          width: 100%;
          padding: 12px 16px;
          background: var(--bg-input, #1a1a24);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          color: var(--text-primary, #e0e0e0);
          font-family: inherit;
          font-size: 0.85rem;
          cursor: pointer;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }

        .lock-btn:hover {
          background: var(--bg-hover, #22222e);
          border-color: var(--status-info, #00aaff);
        }

        .lock-btn.locked {
          background: rgba(0, 170, 255, 0.1);
          border-color: var(--status-info, #00aaff);
          color: var(--status-info, #00aaff);
        }

        .warning-box {
          margin-top: 8px;
          padding: 10px 12px;
          background: rgba(255, 170, 0, 0.1);
          border: 1px solid var(--status-warning, #ffaa00);
          border-radius: 6px;
          font-size: 0.75rem;
          color: var(--status-warning, #ffaa00);
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .warning-box.hidden {
          display: none;
        }

        .railgun-mount-row {
          display: flex;
          gap: 6px;
          margin-bottom: 6px;
        }

        .railgun-mount-row .fire-btn {
          flex: 1;
          padding: 12px 8px;
          font-size: 0.85rem;
          min-height: 52px;
        }

        /* === Missile Salvo Selector === */
        .salvo-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 8px;
        }

        .salvo-label {
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          color: var(--text-secondary, #888899);
          white-space: nowrap;
        }

        .salvo-group {
          display: flex;
          gap: 3px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          padding: 3px;
          flex: 1;
        }

        .salvo-btn {
          flex: 1;
          padding: 5px 4px;
          border: 1px solid transparent;
          border-radius: 4px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.7rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.12s ease;
          min-height: 28px;
        }

        .salvo-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .salvo-btn.active {
          color: #ff8800;
          border-color: #ff8800;
          background: rgba(255, 136, 0, 0.12);
        }

        /* === Missile Flight Profile Selector === */
        .profile-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 8px;
        }

        .profile-label {
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          color: var(--text-secondary, #888899);
          white-space: nowrap;
        }

        .profile-group {
          display: flex;
          gap: 3px;
          background: var(--bg-input, #1a1a24);
          border-radius: 6px;
          padding: 3px;
          flex: 1;
        }

        .profile-btn {
          flex: 1;
          padding: 5px 4px;
          border: 1px solid transparent;
          border-radius: 4px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.6rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.2px;
          cursor: pointer;
          transition: all 0.12s ease;
          min-height: 28px;
          white-space: nowrap;
        }

        .profile-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .profile-btn.active {
          color: #ff8800;
          border-color: #ff8800;
          background: rgba(255, 136, 0, 0.12);
        }

        /* === Authorization Toggle Buttons === */
        .auth-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
        }

        .auth-btn {
          flex: 1;
          padding: 6px 10px;
          border-radius: 6px;
          font-family: inherit;
          font-size: 0.65rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          min-height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          transition: all 0.15s ease;
          border: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
          color: var(--text-dim, #555566);
        }

        .auth-btn:hover {
          border-color: var(--border-active, #3a3a4a);
          color: var(--text-secondary, #888899);
          background: var(--bg-hover, #22222e);
        }

        .auth-btn.authorized {
          border-color: var(--status-nominal, #00ff88);
          color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.08);
          animation: auth-pulse 2s ease-in-out infinite;
        }

        @keyframes auth-pulse {
          0%, 100% {
            box-shadow: 0 0 6px rgba(0, 255, 136, 0.2);
          }
          50% {
            box-shadow: 0 0 14px rgba(0, 255, 136, 0.45), 0 0 4px rgba(0, 255, 136, 0.15);
          }
        }

        .auth-btn .auth-icon {
          font-size: 0.8rem;
          line-height: 1;
        }

        /* Conditions checklist shown below authorized weapon */
        .auth-conditions {
          display: none;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.6rem;
          color: var(--text-dim, #555566);
          margin-top: 4px;
          padding: 4px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          gap: 8px;
          flex-wrap: wrap;
        }

        .auth-conditions.visible {
          display: flex;
        }

        .auth-cond {
          white-space: nowrap;
        }

        .auth-cond.met {
          color: var(--status-nominal, #00ff88);
        }

        .auth-cond.unmet {
          color: var(--status-critical, #ff4444);
        }

        .auth-cond.pending {
          color: var(--status-warning, #ffaa00);
        }

        /* Auto-fire flash overlay */
        @keyframes fire-flash {
          0% { opacity: 1; }
          100% { opacity: 0; }
        }

        .fire-flash-overlay {
          position: absolute;
          inset: 0;
          background: rgba(255, 68, 68, 0.25);
          border-radius: 8px;
          pointer-events: none;
          animation: fire-flash 0.4s ease-out forwards;
        }

        .fire-flash-overlay.missile {
          background: rgba(255, 136, 0, 0.25);
        }

        /* Wrapper for fire button + auth button side by side */
        .fire-auth-row {
          display: flex;
          gap: 6px;
          align-items: stretch;
        }

        .fire-auth-row .fire-btn {
          flex: 1;
        }

        .fire-auth-row .auth-btn {
          flex: 0 0 auto;
          width: 44px;
          min-height: 52px;
        }

        /* Salvo/profile controls only visible when missile type is selected */
        .missile-options {
          display: none;
        }

        .missile-options.visible {
          display: block;
        }

        /* === Tier-specific visibility classes === */
        .tier-hidden { display: none !important; }

        /* MANUAL tier: full controls + munition programming */
        .manual-only { display: none; }
        :host(.tier-manual) .manual-only { display: block; }
        :host(.tier-manual) .auth-row,
        :host(.tier-manual) .auth-conditions { display: none !important; }

        /* ARCADE tier: grouped fire buttons, confidence gate */
        .arcade-grouped-btns {
          display: none;
          gap: 6px;
          margin-bottom: 12px;
        }
        :host(.tier-arcade) .arcade-grouped-btns { display: flex; }
        :host(.tier-arcade) .railgun-mount-row { display: none !important; }
        :host(.tier-arcade) .auth-row { display: none !important; }
        :host(.tier-arcade) .auth-conditions { display: none !important; }

        .arcade-fire-btn {
          flex: 1;
          padding: 14px 10px;
          border-radius: 8px;
          font-size: 0.85rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          cursor: pointer;
          min-height: 56px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          transition: all 0.1s ease;
          font-family: inherit;
        }
        .arcade-fire-btn.railgun {
          background: var(--status-critical, #ff4444);
          border: 2px solid var(--status-critical, #ff4444);
          color: white;
        }
        .arcade-fire-btn.torpedo {
          background: var(--status-nominal, #00ff88);
          border: 2px solid var(--status-nominal, #00ff88);
          color: #0a0a0f;
        }
        .arcade-fire-btn.missile {
          background: #ff8800;
          border: 2px solid #ff8800;
          color: white;
        }
        .arcade-fire-btn:disabled {
          background: var(--bg-input, #1a1a24);
          border-color: var(--border-default, #2a2a3a);
          color: var(--text-dim, #555566);
          cursor: not-allowed;
        }
        .arcade-fire-btn:hover:not(:disabled) {
          filter: brightness(1.1);
          transform: translateY(-1px);
        }
        .arcade-ammo-pct {
          font-size: 0.65rem;
          opacity: 0.85;
        }

        /* CPU-ASSIST tier: auth toggles only, hide manual controls */
        :host(.tier-cpu-assist) .railgun-mount-row { display: none !important; }
        :host(.tier-cpu-assist) .pdc-mode-group { display: none !important; }
        :host(.tier-cpu-assist) .launcher-type-group { display: none !important; }
        :host(.tier-cpu-assist) .missile-options { display: none !important; }
        :host(.tier-cpu-assist) .fire-auth-row .fire-btn { display: none !important; }
        :host(.tier-cpu-assist) #railgun-mounts { display: none !important; }
        :host(.tier-cpu-assist) .fire-hint { display: none !important; }
        :host(.tier-cpu-assist) .cease-fire-btn { display: none !important; }

        .cpuassist-auth-grid {
          display: none;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 6px;
          margin-bottom: 12px;
        }
        :host(.tier-cpu-assist) .cpuassist-auth-grid { display: grid; }

        .cpuassist-auth-card {
          padding: 12px 8px;
          border-radius: 8px;
          text-align: center;
          cursor: pointer;
          transition: all 0.15s ease;
          border: 1px solid var(--border-default, #2a2a3a);
          background: var(--bg-input, #1a1a24);
        }
        .cpuassist-auth-card.authorized {
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.06);
        }
        .cpuassist-auth-card:hover {
          border-color: var(--text-secondary, #888899);
        }
        .cpuassist-auth-card .auth-weapon-name {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--text-dim, #555566);
          margin-bottom: 4px;
        }
        .cpuassist-auth-card.authorized .auth-weapon-name {
          color: var(--status-nominal, #00ff88);
        }
        .cpuassist-auth-card .auth-toggle-label {
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          color: var(--text-dim, #555566);
        }
        .cpuassist-auth-card.authorized .auth-toggle-label {
          color: var(--status-nominal, #00ff88);
        }

        /* === Auto-Tactical Engagement Rules (CPU-ASSIST) === */
        .engagement-panel {
          display: none;
          margin-bottom: 16px;
          padding: 12px;
          background: rgba(128, 0, 255, 0.06);
          border: 1px solid rgba(128, 0, 255, 0.3);
          border-radius: 8px;
        }

        .engagement-panel.visible { display: block; }

        .engagement-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .engagement-title {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: #bb88ff;
        }

        .engagement-toggle {
          padding: 4px 10px;
          border-radius: 4px;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.65rem;
          font-weight: 700;
          cursor: pointer;
          border: 1px solid rgba(128, 0, 255, 0.4);
          background: transparent;
          color: var(--text-dim, #555566);
          transition: all 0.15s ease;
        }

        .engagement-toggle.active {
          border-color: #bb88ff;
          color: #bb88ff;
          background: rgba(128, 0, 255, 0.15);
        }

        .engagement-mode-group {
          display: flex;
          gap: 4px;
          background: var(--bg-input, #1a1a24);
          border-radius: 8px;
          padding: 4px;
          margin-bottom: 8px;
        }

        .engagement-mode-btn {
          flex: 1;
          padding: 8px 4px;
          border: 1px solid transparent;
          border-radius: 6px;
          background: transparent;
          color: var(--text-dim, #555566);
          font-family: inherit;
          font-size: 0.6rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.2px;
          cursor: pointer;
          transition: all 0.15s ease;
          min-height: 34px;
        }

        .engagement-mode-btn:hover {
          color: var(--text-primary, #e0e0e0);
          background: rgba(255, 255, 255, 0.05);
        }

        .engagement-mode-btn.active {
          color: #bb88ff;
          border-color: #bb88ff;
          background: rgba(128, 0, 255, 0.12);
        }

        .engagement-mode-btn.active.weapons-free {
          color: var(--status-critical, #ff4444);
          border-color: var(--status-critical, #ff4444);
          background: rgba(255, 68, 68, 0.1);
        }

        .engagement-mode-btn.active.defensive {
          color: var(--status-nominal, #00ff88);
          border-color: var(--status-nominal, #00ff88);
          background: rgba(0, 255, 136, 0.1);
        }

        /* Proposal cards — shared styles from proposal-styles.js */
        ${getProposalCSS()}
      </style>

      <!-- Auto-Tactical Engagement Panel (CPU-ASSIST tier) -->
      <div class="engagement-panel" id="engagement-panel">
        <div class="engagement-header">
          <span class="engagement-title">Auto-Tactical</span>
          <button class="engagement-toggle" id="engagement-toggle">ENABLE</button>
        </div>
        <div class="engagement-mode-group" id="engagement-mode-group">
          <button class="engagement-mode-btn weapons-free" data-mode="weapons_free">WEAPONS FREE</button>
          <button class="engagement-mode-btn" data-mode="weapons_hold">WEAPONS HOLD</button>
          <button class="engagement-mode-btn defensive" data-mode="defensive_only">DEFENSIVE</button>
        </div>
        <div id="tactical-proposals"></div>
      </div>

      <!-- ARCADE tier: grouped fire buttons (RAILGUN / TORPEDO / MISSILE) -->
      <div class="arcade-grouped-btns" id="arcade-grouped-btns">
        <button class="arcade-fire-btn railgun" id="arcade-fire-railgun" disabled>
          RAILGUN
          <span class="arcade-ammo-pct" id="arcade-rg-ammo">0%</span>
        </button>
        <button class="arcade-fire-btn torpedo" id="arcade-fire-torpedo" disabled>
          TORPEDO
          <span class="arcade-ammo-pct" id="arcade-trp-ammo">0%</span>
        </button>
        <button class="arcade-fire-btn missile" id="arcade-fire-missile" disabled>
          MISSILE
          <span class="arcade-ammo-pct" id="arcade-msl-ammo">0%</span>
        </button>
      </div>

      <!-- CPU-ASSIST tier: per-weapon-type authorize toggles -->
      <div class="cpuassist-auth-grid" id="cpuassist-auth-grid">
        <div class="cpuassist-auth-card" id="cpuassist-auth-railgun" data-weapon="railgun">
          <div class="auth-weapon-name">Railgun</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
        <div class="cpuassist-auth-card" id="cpuassist-auth-torpedo" data-weapon="torpedo">
          <div class="auth-weapon-name">Torpedo</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
        <div class="cpuassist-auth-card" id="cpuassist-auth-missile" data-weapon="missile">
          <div class="auth-weapon-name">Missile</div>
          <div class="auth-toggle-label">AUTHORIZE</div>
        </div>
      </div>

      <div class="ammo-heat-hud" id="ammo-heat-hud"></div>

      <div class="weapon-group target-lock-row">
        <div class="group-title">Target Lock</div>
        <button class="lock-btn" id="lock-btn" data-testid="lock-btn">
          LOCK TARGET
        </button>
      </div>

      <div class="weapon-group" id="railgun-group">
        <div class="group-title">Railgun</div>
        <div id="railgun-mounts"></div>
        <div class="auth-row">
          <button class="auth-btn" id="auth-railgun" data-weapon="railgun" data-testid="auth-railgun"
                  title="Authorize continuous railgun fire when conditions are met">
            <span class="auth-icon">&#x1f512;</span> AUTH
          </button>
        </div>
        <div class="auth-conditions" id="auth-cond-railgun"></div>
        <div class="fire-hint" id="railgun-hint"></div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Point Defense</div>
        <div class="pdc-mode-group" id="pdc-mode-group" data-testid="pdc-mode-group">
          <button class="pdc-mode-btn active" data-mode="auto" data-testid="pdc-auto">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>AUTO</span>
          </button>
          <button class="pdc-mode-btn" data-mode="manual" data-testid="pdc-manual">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>MANUAL</span>
          </button>
          <button class="pdc-mode-btn" data-mode="hold_fire" data-testid="pdc-hold">
            <span class="pdc-mode-label"><span class="pdc-indicator"></span>HOLD</span>
          </button>
        </div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Launcher</div>
        <div class="launcher-type-group" id="launcher-type-group" data-testid="launcher-type-group">
          <button class="launcher-type-btn active" data-type="torpedo" data-testid="launcher-torpedo">
            <span class="launcher-type-label"><span class="launcher-type-indicator"></span>TORPEDO</span>
          </button>
          <button class="launcher-type-btn" data-type="missile" data-testid="launcher-missile">
            <span class="launcher-type-label"><span class="launcher-type-indicator"></span>MISSILE</span>
          </button>
        </div>

        <!-- Missile-only options: salvo size + flight profile -->
        <div class="missile-options" id="missile-options">
          <div class="salvo-row">
            <span class="salvo-label">Salvo</span>
            <div class="salvo-group" id="salvo-group" data-testid="salvo-group">
              <button class="salvo-btn active" data-salvo="1">1x</button>
              <button class="salvo-btn" data-salvo="2">2x</button>
              <button class="salvo-btn" data-salvo="4">4x</button>
              <button class="salvo-btn" data-salvo="all">ALL</button>
            </div>
          </div>
          <div class="profile-row">
            <span class="profile-label">Profile</span>
            <div class="profile-group" id="profile-group" data-testid="profile-group">
              <button class="profile-btn active" data-profile="direct">DIRECT</button>
              <button class="profile-btn" data-profile="evasive">EVASIVE</button>
              <button class="profile-btn" data-profile="terminal_pop">T-POP</button>
              <button class="profile-btn" data-profile="bracket">BRACKET</button>
            </div>
          </div>
        </div>

        <div class="fire-auth-row" id="launcher-fire-row" style="position: relative;">
          <button class="fire-btn torpedo-btn" id="launcher-fire-btn" data-testid="launcher-fire-btn">
            FIRE TORPEDO
            <span class="torpedo-count" id="launcher-count">(0)</span>
          </button>
          <button class="auth-btn" id="auth-torpedo" data-weapon="torpedo" data-testid="auth-torpedo"
                  title="Authorize auto-fire when conditions are met (single fire)">
            <span class="auth-icon">&#x1f512;</span>
          </button>
          <button class="auth-btn" id="auth-missile" data-weapon="missile" data-testid="auth-missile"
                  title="Authorize auto-fire salvo when conditions are met" style="display: none;">
            <span class="auth-icon">&#x1f512;</span>
          </button>
        </div>
        <div class="auth-conditions" id="auth-cond-torpedo"></div>
        <div class="auth-conditions" id="auth-cond-missile"></div>
        <div class="warning-box hidden" id="no-lock-warning">
          No target lock - ordnance will fire dumb
        </div>

        <!-- MANUAL tier: munition programming interface -->
        <div class="manual-only" id="munition-program-section">
          <div class="group-title" style="margin-top: 12px;">MUNITION PROGRAMMING</div>
          <div class="manual-solution-grid" style="display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; font-size: 0.72rem; padding: 8px;">
            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">GUIDANCE</span>
            <select id="prog-guidance" style="background: var(--bg-input, #1a1a24); color: var(--text-primary, #e0e0e0); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; font-size: 0.72rem; font-family: var(--font-mono);">
              <option value="dumb">DUMB (no corrections)</option>
              <option value="guided" selected>GUIDED (PN gain 4.0)</option>
              <option value="smart">SMART (PN gain 6.0)</option>
            </select>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">PN GAIN</span>
            <input id="prog-pn-gain" type="number" min="1.0" max="8.0" step="0.5" value="4.0"
              style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; width: 60px; font-family: var(--font-mono); font-size: 0.72rem;">

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">WARHEAD</span>
            <select id="prog-warhead" style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; font-size: 0.72rem; font-family: var(--font-mono);">
              <option value="fragmentation" selected>FRAGMENTATION</option>
              <option value="shaped_charge">SHAPED CHARGE</option>
              <option value="emp">EMP</option>
            </select>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">FUSE DIST</span>
            <span style="display:flex;align-items:center;gap:4px;">
              <input id="prog-fuse" type="number" min="5" max="200" step="5" value="50"
                style="background: var(--bg-input, #1a1a24); color: var(--text-primary); border: 1px solid var(--border-default, #2a2a3a); padding: 2px 4px; width: 50px; font-family: var(--font-mono); font-size: 0.72rem;">
              <span style="color: var(--text-dim); font-size: 0.65rem;">m</span>
            </span>

            <span class="ms-label" style="color: var(--text-dim); text-transform: uppercase; font-size: 0.65rem;">DATALINK</span>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input id="prog-datalink" type="checkbox" checked style="accent-color: var(--tier-accent, #ff8800);">
              <span style="color: var(--text-primary); font-size: 0.72rem;">Active</span>
            </label>
          </div>
          <button id="prog-upload-btn" style="
            width: 100%; padding: 6px; margin-top: 6px;
            background: rgba(255, 136, 0, 0.1); border: 1px solid var(--tier-accent, #ff8800);
            color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
            font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: 1px; cursor: pointer; border-radius: 2px;
          ">UPLOAD PROGRAM</button>
          <div id="prog-status" style="font-size: 0.65rem; color: var(--text-dim); margin-top: 4px; text-align: center;"></div>
        </div>

        <!-- MANUAL tier: dumb-fire (no targeting lock required) -->
        <div class="manual-only" id="unguided-fire-section" style="margin-top: 12px;">
          <div class="group-title">UNGUIDED FIRE (BORE-SIGHT)</div>
          <div style="display: flex; gap: 6px;">
            <button id="fire-unguided-railgun" style="
              flex: 1; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">RAILGUN</button>
            <button id="fire-unguided-pdc" style="
              flex: 1; padding: 8px; cursor: pointer;
              background: rgba(255, 136, 0, 0.08); border: 1px solid var(--tier-accent, #ff8800);
              color: var(--tier-accent, #ff8800); font-family: var(--font-mono);
              font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.5px; border-radius: 2px;
            ">PDC BURST</button>
          </div>
          <div style="font-size: 0.6rem; color: var(--text-dim); margin-top: 4px; text-align: center; font-style: italic;">
            Fires along ship heading — no lock required
          </div>
        </div>
      </div>

      <div class="weapon-group">
        <div class="group-title">Damage Assessment</div>
        <button class="assess-btn" id="assess-btn" data-testid="assess-btn">
          ASSESS TARGET DAMAGE
        </button>
        <div id="assessment-results"></div>
      </div>

      <div class="weapon-group">
        <button class="cease-fire-btn" id="cease-fire-btn" data-testid="cease-fire-btn">CEASE FIRE</button>
      </div>
    `;
  }

  /**
   * Apply tier class to :host and toggle tier-specific element visibility.
   * MANUAL: individual mount fire buttons only, raw ammo count, no solution preview.
   * RAW: per-mount status with solution data, ammo, heat, charge state. (default, all controls visible)
   * ARCADE: grouped fire buttons (RAILGUN/TORPEDO/MISSILE), confidence gate, ammo as percentage.
   * CPU-ASSIST: authorize toggles per weapon type, auto-fires when conditions met.
   */
  _applyTier() {
    const host = this;
    host.classList.remove("tier-manual", "tier-raw", "tier-arcade", "tier-cpu-assist");
    host.classList.add(`tier-${this._tier}`);
    this._updateDisplay();
  }

  _setupInteraction() {
    // ARCADE: grouped fire buttons
    this.shadowRoot.getElementById("arcade-fire-railgun").addEventListener("click", () => {
      // Fire first ready railgun mount
      const weapons = stateManager.getWeapons();
      const truthWeapons = weapons?.truth_weapons || {};
      const railgun = Object.entries(truthWeapons).find(
        ([id, w]) => id.startsWith("railgun") && w.solution?.ready_to_fire && !w.reloading && (w.ammo ?? 0) > 0
      );
      if (railgun) this._fireRailgun(railgun[0]);
    });

    this.shadowRoot.getElementById("arcade-fire-torpedo").addEventListener("click", () => {
      this._fireLauncher();
    });

    this.shadowRoot.getElementById("arcade-fire-missile").addEventListener("click", () => {
      this._missileProfile = "direct";
      this._salvoSize = 1;
      this._fireMissileSalvo();
    });

    // CPU-ASSIST: auth card toggles
    this.shadowRoot.querySelectorAll(".cpuassist-auth-card").forEach((card) => {
      card.addEventListener("click", () => {
        this._toggleAuth(card.dataset.weapon);
      });
    });

    // Auto-tactical engagement toggle
    this.shadowRoot.getElementById("engagement-toggle").addEventListener("click", () => {
      this._toggleAutoTactical();
    });

    // Engagement mode selector
    this.shadowRoot.getElementById("engagement-mode-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".engagement-mode-btn");
      if (btn) {
        wsClient.sendShipCommand("set_engagement_rules", { mode: btn.dataset.mode });
      }
    });

    // Tactical proposal approve/deny (delegated)
    this.shadowRoot.getElementById("tactical-proposals").addEventListener("click", (e) => {
      const approveBtn = e.target.closest(".proposal-approve");
      const denyBtn = e.target.closest(".proposal-deny");
      if (approveBtn) {
        wsClient.sendShipCommand("approve_tactical", { proposal_id: approveBtn.dataset.id });
      } else if (denyBtn) {
        wsClient.sendShipCommand("deny_tactical", { proposal_id: denyBtn.dataset.id });
      }
    });

    // Lock/Unlock target
    this.shadowRoot.getElementById("lock-btn").addEventListener("click", () => {
      this._toggleTargetLock();
    });

    // Launcher type toggle (torpedo / missile)
    this.shadowRoot.getElementById("launcher-type-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".launcher-type-btn");
      if (btn) {
        this._setLauncherType(btn.dataset.type);
      }
    });

    // Fire launcher (torpedo or missile based on selected type)
    this.shadowRoot.getElementById("launcher-fire-btn").addEventListener("click", () => {
      if (this._launcherType === "missile") {
        this._fireMissileSalvo();
      } else {
        this._fireLauncher();
      }
    });

    // Missile salvo size selector
    this.shadowRoot.getElementById("salvo-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".salvo-btn");
      if (btn) {
        this._setSalvoSize(btn.dataset.salvo);
      }
    });

    // Missile flight profile selector
    this.shadowRoot.getElementById("profile-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".profile-btn");
      if (btn) {
        this._setMissileProfile(btn.dataset.profile);
      }
    });

    // PDC mode buttons
    this.shadowRoot.getElementById("pdc-mode-group").addEventListener("click", (e) => {
      const btn = e.target.closest(".pdc-mode-btn");
      if (btn) {
        this._setPdcMode(btn.dataset.mode);
      }
    });

    // Authorization toggle buttons
    this.shadowRoot.querySelectorAll(".auth-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._toggleAuth(btn.dataset.weapon);
      });
    });

    // Assess damage
    this.shadowRoot.getElementById("assess-btn").addEventListener("click", () => {
      this._assessDamage();
    });

    // Cease fire — also de-authorizes all weapons
    this.shadowRoot.getElementById("cease-fire-btn").addEventListener("click", () => {
      this._ceaseFire();
    });

    // MANUAL tier: munition programming upload
    const progUploadBtn = this.shadowRoot.getElementById("prog-upload-btn");
    if (progUploadBtn) {
      progUploadBtn.addEventListener("click", () => this._uploadMunitionProgram());
    }

    // MANUAL tier: guidance mode updates PN gain default
    const progGuidance = this.shadowRoot.getElementById("prog-guidance");
    if (progGuidance) {
      progGuidance.addEventListener("change", () => {
        const pnInput = this.shadowRoot.getElementById("prog-pn-gain");
        if (!pnInput) return;
        const defaults = { dumb: 0, guided: 4.0, smart: 6.0 };
        pnInput.value = defaults[progGuidance.value] ?? 4.0;
      });
    }

    // MANUAL tier: unguided fire buttons
    const unguidedRailgun = this.shadowRoot.getElementById("fire-unguided-railgun");
    if (unguidedRailgun) {
      unguidedRailgun.addEventListener("click", () => {
        wsClient.sendShipCommand("fire_unguided", { weapon_type: "railgun" });
      });
    }
    const unguidedPdc = this.shadowRoot.getElementById("fire-unguided-pdc");
    if (unguidedPdc) {
      unguidedPdc.addEventListener("click", () => {
        wsClient.sendShipCommand("fire_unguided", { weapon_type: "pdc" });
      });
    }
  }

  _uploadMunitionProgram() {
    const guidance = this.shadowRoot.getElementById("prog-guidance")?.value || "guided";
    const pnGain = parseFloat(this.shadowRoot.getElementById("prog-pn-gain")?.value) || 4.0;
    const warhead = this.shadowRoot.getElementById("prog-warhead")?.value || "fragmentation";
    const fuse = parseFloat(this.shadowRoot.getElementById("prog-fuse")?.value) || 50;
    const datalink = this.shadowRoot.getElementById("prog-datalink")?.checked ?? true;

    const program = {
      munition_type: this._launcherType || "torpedo",
      guidance_mode: guidance,
      pn_gain: Math.max(1.0, Math.min(8.0, pnGain)),
      warhead_type: warhead,
      fuse_distance: Math.max(5, Math.min(200, fuse)),
      datalink: datalink,
    };

    wsClient.sendShipCommand("program_munition", program);

    const statusEl = this.shadowRoot.getElementById("prog-status");
    if (statusEl) {
      statusEl.textContent = `${program.munition_type.toUpperCase()} programmed: ${guidance.toUpperCase()}, PN=${program.pn_gain}, ${warhead.toUpperCase()}, fuse=${program.fuse_distance}m`;
      statusEl.style.color = "var(--tier-accent, #ff8800)";
    }
  }

  _updateDisplay() {
    const targeting = stateManager.getTargeting();
    const weapons = stateManager.getWeapons();
    const combat = stateManager.getCombat();
    const ship = stateManager.getShipState();

    // Update ammo/heat HUD (above all fire controls)
    this._updateAmmoHeatHud(weapons);

    // Update target lock button
    const lockBtn = this.shadowRoot.getElementById("lock-btn");
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasLock = lockedTarget != null && lockState !== "none";

    if (hasLock) {
      lockBtn.classList.add("locked");
      const stateLabel = lockState === "locked" ? "LOCKED" : lockState.toUpperCase();
      lockBtn.textContent = `${stateLabel}: ${lockedTarget}`;
    } else {
      lockBtn.classList.remove("locked");
      lockBtn.textContent = "LOCK TARGET";
    }

    // No-lock warning
    const noLockWarning = this.shadowRoot.getElementById("no-lock-warning");
    noLockWarning.classList.toggle("hidden", hasLock);

    // Railgun mounts — truth_weapons lives in weapons telemetry, not combat
    this._updateRailgunMounts(weapons, targeting, hasLock);

    // PDC mode from weapons telemetry (combat state is merged into weapons by server)
    const currentPdcMode = weapons?.pdc_mode || combat?.pdc_mode || "auto";
    this._pdcMode = currentPdcMode;
    this.shadowRoot.querySelectorAll(".pdc-mode-btn").forEach((btn) => {
      const isActive = btn.dataset.mode === currentPdcMode;
      btn.classList.toggle("active", isActive);
      if (btn.dataset.mode === "hold_fire") {
        btn.classList.toggle("hold-fire", isActive);
      }
    });

    // Launcher type toggle visual state
    this.shadowRoot.querySelectorAll(".launcher-type-btn").forEach((btn) => {
      const isActive = btn.dataset.type === this._launcherType;
      btn.classList.toggle("active", isActive);
      btn.classList.toggle("missile", isActive && btn.dataset.type === "missile");
    });

    // Show/hide missile-specific options (salvo size, flight profile)
    const isMissile = this._launcherType === "missile";
    const missileOpts = this.shadowRoot.getElementById("missile-options");
    missileOpts.classList.toggle("visible", isMissile);

    // Show correct auth button for current launcher type
    const authTorpedo = this.shadowRoot.getElementById("auth-torpedo");
    const authMissile = this.shadowRoot.getElementById("auth-missile");
    authTorpedo.style.display = isMissile ? "none" : "";
    authMissile.style.display = isMissile ? "" : "none";

    // Salvo selector visual state
    this.shadowRoot.querySelectorAll(".salvo-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.salvo === String(this._salvoSize));
    });

    // Flight profile selector visual state
    this.shadowRoot.querySelectorAll(".profile-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.profile === this._missileProfile);
    });

    // Launcher fire button — adapts to selected type (torpedo or missile)
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;
    const missileData = weapons?.missiles || {};
    const missileCount = missileData.loaded ?? missileData.count ?? 0;

    const fireBtn = this.shadowRoot.getElementById("launcher-fire-btn");
    const activeCount = isMissile ? missileCount : torpedoCount;

    fireBtn.disabled = activeCount <= 0 || !hasLock;

    // Switch button style and label based on launcher type
    fireBtn.classList.toggle("torpedo-btn", !isMissile);
    fireBtn.classList.toggle("missile-btn", isMissile);
    fireBtn.textContent = "";

    if (isMissile) {
      // Resolve effective salvo size for the label
      const effectiveSalvo = this._getEffectiveSalvoSize(missileCount);
      fireBtn.append(document.createTextNode(`FIRE MISSILE x${effectiveSalvo} `));
    } else {
      fireBtn.append(document.createTextNode("FIRE TORPEDO "));
    }
    const newCountSpan = document.createElement("span");
    newCountSpan.className = "torpedo-count";
    newCountSpan.id = "launcher-count";
    newCountSpan.textContent = `(${activeCount} remaining)`;
    fireBtn.appendChild(newCountSpan);

    // Update authorization button visuals
    this._updateAuthButtons(weapons, targeting, hasLock);

    // --- Auto-execute queue: fire authorized weapons when conditions are met ---
    this._processAutoExecute(weapons, targeting, hasLock);

    // Assess button - needs a lock
    const assessBtn = this.shadowRoot.getElementById("assess-btn");
    assessBtn.disabled = !hasLock;

    // Render assessment data if available
    this._renderAssessment();

    // Update auto-tactical engagement panel (CPU-ASSIST tier)
    this._updateEngagementPanel();

    // --- Tier-specific updates ---
    this._updateArcadeButtons(weapons, targeting, hasLock);
    this._updateCpuAssistAuthCards();
  }

  /**
   * Render the compact ammo/heat summary HUD.
   * Shows per-weapon-type ammo counts, aggregate heat bar,
   * and reload status for any weapon currently cycling.
   */
  _updateAmmoHeatHud(weapons) {
    const hud = this.shadowRoot.getElementById("ammo-heat-hud");
    if (!hud) return;

    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};

    // Aggregate ammo by weapon type (railgun, pdc) from truth_weapons
    const ammoByType = {};
    let totalHeat = 0;
    let totalMaxHeat = 0;
    const reloading = [];

    for (const [mountId, w] of Object.entries(truthWeapons)) {
      const wtype = w.weapon_type || (mountId.startsWith("pdc") ? "pdc" : "railgun");
      if (!ammoByType[wtype]) {
        ammoByType[wtype] = { current: 0, capacity: 0 };
      }
      ammoByType[wtype].current += w.ammo ?? 0;
      ammoByType[wtype].capacity += w.ammo_capacity ?? 0;

      totalHeat += w.heat ?? 0;
      totalMaxHeat += w.max_heat ?? 0;

      if (w.reloading) {
        const pct = Math.round((w.reload_progress ?? 0) * 100);
        const displayName = mountId.replace(/_/g, " ").toUpperCase();
        reloading.push({ name: displayName, pct });
      }
    }

    // Torpedo/missile ammo
    const trpLoaded = torpedoData.loaded ?? torpedoData.count ?? 0;
    const trpCapacity = torpedoData.capacity ?? trpLoaded;
    const mslLoaded = missileData.loaded ?? missileData.count ?? 0;
    const mslCapacity = missileData.capacity ?? mslLoaded;

    // Torpedo/missile cooldowns count as reloading
    if ((torpedoData.cooldown ?? 0) > 0) {
      reloading.push({ name: "TORPEDO TUBE", pct: null, cooldown: torpedoData.cooldown });
    }
    if ((missileData.cooldown ?? 0) > 0) {
      reloading.push({ name: "MISSILE BAY", pct: null, cooldown: missileData.cooldown });
    }

    // If no weapons data at all, show minimal state
    const hasAnyData = Object.keys(truthWeapons).length > 0 || trpCapacity > 0 || mslCapacity > 0;
    if (!hasAnyData) {
      hud.innerHTML = `
        <div class="ammo-summary">
          <span class="ammo-item">
            <span class="ammo-label">WEAPONS</span>
            <span class="ammo-value empty">NO DATA</span>
          </span>
        </div>
      `;
      return;
    }

    // Build ammo summary items
    const ammoItems = [];
    // Type abbreviation map
    const typeLabels = { railgun: "RG", pdc: "PDC" };

    for (const [wtype, data] of Object.entries(ammoByType)) {
      const label = typeLabels[wtype] || wtype.toUpperCase();
      const ratio = data.capacity > 0 ? data.current / data.capacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">${label}:</span>` +
        `<span class="ammo-value ${colorClass}">${data.current}/${data.capacity}</span>` +
        `</span>`
      );
    }

    // Torpedoes (only show if ship has tubes)
    if (trpCapacity > 0) {
      const ratio = trpCapacity > 0 ? trpLoaded / trpCapacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">TRP:</span>` +
        `<span class="ammo-value ${colorClass}">${trpLoaded}/${trpCapacity}</span>` +
        `</span>`
      );
    }

    // Missiles (only show if ship has launchers)
    if (mslCapacity > 0) {
      const ratio = mslCapacity > 0 ? mslLoaded / mslCapacity : 1;
      const colorClass = ratio <= 0 ? "empty" : ratio <= 0.15 ? "critical" : ratio <= 0.35 ? "low" : "";
      ammoItems.push(
        `<span class="ammo-item">` +
        `<span class="ammo-label">MSL:</span>` +
        `<span class="ammo-value ${colorClass}">${mslLoaded}/${mslCapacity}</span>` +
        `</span>`
      );
    }

    // Ammo line with separators
    const ammoHtml = ammoItems.join(`<span class="ammo-separator">|</span>`);

    // Heat bar (aggregate across all truth_weapons)
    let heatHtml = "";
    if (totalMaxHeat > 0) {
      const heatPct = Math.round((totalHeat / totalMaxHeat) * 100);
      const heatClass = heatPct >= 80 ? "hot" : heatPct >= 50 ? "warm" : "cool";
      heatHtml = `
        <div class="heat-bar-section">
          <div class="heat-bar-header">
            <span class="heat-bar-label">WEAPONS HEAT</span>
            <span class="heat-bar-value ${heatClass}">${Math.round(totalHeat)}/${Math.round(totalMaxHeat)}</span>
          </div>
          <div class="heat-bar-container">
            <div class="heat-bar-fill ${heatClass}" style="width: ${Math.min(heatPct, 100)}%"></div>
          </div>
        </div>
      `;
    }

    // Reload status
    let reloadHtml = "";
    if (reloading.length > 0) {
      const items = reloading.map((r) => {
        const statusText = r.pct != null
          ? `${r.name} ${r.pct}%`
          : `${r.name} ${r.cooldown.toFixed(1)}s`;
        return `<span class="reload-item"><span class="reload-indicator"></span>${statusText}</span>`;
      }).join("");
      reloadHtml = `<div class="reload-status">${items}</div>`;
    }

    hud.innerHTML = `
      <div class="ammo-summary">${ammoHtml}</div>
      ${heatHtml}
      ${reloadHtml}
    `;
  }

  _updateRailgunMounts(weapons, targeting, hasLock) {
    const mountsContainer = this.shadowRoot.getElementById("railgun-mounts");
    const hintEl = this.shadowRoot.getElementById("railgun-hint");
    const truthWeapons = weapons?.truth_weapons || {};

    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));

    if (railguns.length === 0) {
      mountsContainer.innerHTML = "";
      hintEl.textContent = "No railgun mounts";
      return;
    }

    let html = '<div class="railgun-mount-row">';
    for (const [mountId, w] of railguns) {
      const ammo = w.ammo ?? 0;
      const ready = w.solution?.ready_to_fire && ammo > 0 && !w.reloading;
      const disabled = !ready || !hasLock ? "disabled" : "";
      const displayName = mountId.replace(/_/g, " ").toUpperCase();
      // Surface the firing solution reason as a tooltip so the player
      // knows WHY the fire button is disabled (arc, range, cycling, etc.)
      const reason = w.solution?.reason || "";
      const tooltip = disabled && reason ? ` title="${reason}"` : "";

      // Charge state indicator for railgun capacitor
      const chargeTime = w.charge_time ?? 0;
      const chargeState = w.charge_state ?? "idle";
      const chargePct = Math.round((w.charge_progress ?? 0) * 100);
      let chargeLabel = "";
      if (chargeTime > 0 && chargeState === "charging") {
        chargeLabel = ` [${chargePct}%]`;
      }

      html += `
        <button class="fire-btn railgun-btn" data-mount="${mountId}" ${disabled}${tooltip}
                data-testid="fire-${mountId}">
          ${displayName} (${ammo})${chargeLabel}
        </button>
      `;
    }
    html += "</div>";

    mountsContainer.innerHTML = html;

    // Bind fire handlers
    mountsContainer.querySelectorAll(".railgun-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._fireRailgun(btn.dataset.mount);
      });
    });

    // Hint — show specific reason when solution exists but isn't ready
    if (!hasLock) {
      hintEl.textContent = "Lock target to fire";
    } else {
      const anyReady = railguns.some(([, w]) => w.solution?.ready_to_fire);
      const anyCharging = railguns.some(
        ([, w]) => (w.charge_time ?? 0) > 0 && w.charge_state === "charging"
      );
      if (anyReady) {
        hintEl.textContent = "";
      } else if (anyCharging) {
        hintEl.textContent = "Capacitor charging...";
      } else {
        // Show the most informative reason from any railgun's solution
        const reasons = railguns
          .map(([, w]) => w.solution?.reason)
          .filter(Boolean);
        const arcReason = reasons.find((r) => r.includes("arc"));
        hintEl.textContent = arcReason || reasons[0] || "Waiting for firing solution";
      }
    }
  }

  _renderAssessment() {
    const container = this.shadowRoot.getElementById("assessment-results");
    if (!this._assessmentData || !this._assessmentData.ok) {
      container.innerHTML = "";
      return;
    }

    const data = this._assessmentData;
    const subsystems = data.subsystems || {};
    const quality = data.assessment_quality ?? 0;

    let html = '<div class="assessment-results">';
    for (const [name, info] of Object.entries(subsystems)) {
      const healthPct = info.health != null ? `${Math.round(info.health * 100)}%` : "???";
      const status = info.status || "unknown";
      html += `
        <div class="assessment-row">
          <span class="assessment-label">${name}</span>
          <span class="assessment-value ${status}">${healthPct} ${status.toUpperCase()}</span>
        </div>
      `;
    }
    html += `
      <div class="assessment-confidence">
        Sensor confidence: ${Math.round(quality * 100)}%
      </div>
    </div>`;

    container.innerHTML = html;
  }

  async _toggleTargetLock() {
    const targeting = stateManager.getTargeting();
    const lockState = targeting?.lock_state || "none";
    const lockedTarget = targeting?.locked_target || null;
    const hasLock = lockedTarget != null && lockState !== "none";

    if (hasLock) {
      try {
        await wsClient.sendShipCommand("unlock_target", {});
        this._assessmentData = null;
      } catch (error) {
        console.error("Unlock target failed:", error);
      }
    } else {
      // Use the selected contact from sensor panel
      const contactId = this._selectedContact;
      if (contactId) {
        try {
          await wsClient.sendShipCommand("designate_target", { contact_id: contactId });
        } catch (error) {
          console.error("Designate target failed:", error);
        }
      }
    }
  }

  async _fireRailgun(mountId) {
    try {
      await wsClient.sendShipCommand("fire_railgun", { mount_id: mountId });
    } catch (error) {
      console.error("Fire railgun failed:", error);
    }
  }

  async _setPdcMode(mode) {
    try {
      await wsClient.sendShipCommand("set_pdc_mode", { mode });
    } catch (error) {
      console.error("Set PDC mode failed:", error);
    }
  }

  _setLauncherType(type) {
    if (type !== "torpedo" && type !== "missile") return;
    this._launcherType = type;
    this._updateDisplay();
  }

  async _fireLauncher() {
    // Torpedo: always single fire, with profile param.
    // Read ARCADE munition config if available (set by munition-config-game).
    const cfg = window._munitionConfig || {};
    const params = { profile: "direct" };
    if (cfg.warhead_type) params.warhead_type = cfg.warhead_type;
    if (cfg.guidance_mode) params.guidance_mode = cfg.guidance_mode;
    try {
      await wsClient.sendShipCommand("launch_torpedo", params);
    } catch (error) {
      console.error("launch_torpedo failed:", error);
    }
  }

  /**
   * Fire a missile salvo: sends launch_missile N times with 100ms stagger.
   * Staggered launch overwhelms PDC coverage by spreading arrival windows.
   */
  async _fireMissileSalvo() {
    const weapons = stateManager.getWeapons();
    const missileData = weapons?.missiles || {};
    const remaining = missileData.loaded ?? missileData.count ?? 0;
    if (remaining <= 0) return;

    const salvoSize = this._getEffectiveSalvoSize(remaining);
    if (salvoSize <= 0) return;

    this._salvoInProgress = true;

    // Show fire flash
    this._showFireFlash("missile");

    // Read ARCADE munition config if available (set by munition-config-game).
    const cfg = window._munitionConfig || {};
    const launchParams = { profile: this._missileProfile };
    if (cfg.warhead_type) launchParams.warhead_type = cfg.warhead_type;
    if (cfg.guidance_mode) launchParams.guidance_mode = cfg.guidance_mode;
    if (cfg.flight_profile) launchParams.profile = cfg.flight_profile;

    for (let i = 0; i < salvoSize; i++) {
      setTimeout(() => {
        wsClient.sendShipCommand("launch_missile", launchParams)
          .catch((err) => console.error(`Salvo missile ${i + 1} failed:`, err));

        // Mark salvo complete after the last missile launches
        if (i === salvoSize - 1) {
          this._salvoInProgress = false;
        }
      }, i * 100);
    }
  }

  /**
   * Resolve the effective salvo size based on the selector value and
   * the number of missiles remaining. "all" fires everything.
   */
  _getEffectiveSalvoSize(remaining) {
    if (this._salvoSize === "all") return Math.max(remaining, 0);
    const requested = parseInt(this._salvoSize, 10);
    if (isNaN(requested) || requested < 1) return 1;
    return Math.min(requested, remaining);
  }

  _setSalvoSize(value) {
    this._salvoSize = value === "all" ? "all" : parseInt(value, 10) || 1;
    this._updateDisplay();
  }

  _setMissileProfile(profile) {
    const valid = ["direct", "evasive", "terminal_pop", "bracket"];
    if (!valid.includes(profile)) return;
    this._missileProfile = profile;
    this._updateDisplay();
  }

  // --- Authorization / Auto-Execute ---

  _toggleAuth(weapon) {
    if (!this._authorized.hasOwnProperty(weapon)) return;
    this._authorized[weapon] = !this._authorized[weapon];
    this._updateDisplay();
  }

  /**
   * Update authorization button visuals and conditions checklists.
   */
  _updateAuthButtons(weapons, targeting, hasLock) {
    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};

    // -- Railgun auth --
    const authRailgun = this.shadowRoot.getElementById("auth-railgun");
    const condRailgun = this.shadowRoot.getElementById("auth-cond-railgun");
    authRailgun.classList.toggle("authorized", this._authorized.railgun);
    authRailgun.querySelector(".auth-icon").textContent = this._authorized.railgun ? "\u{1f513}" : "\u{1f512}";
    authRailgun.title = this._authorized.railgun
      ? "Click to de-authorize railgun auto-fire"
      : "Authorize continuous railgun fire when conditions are met";

    // Railgun conditions
    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));
    const anyRailgunReady = railguns.some(([, w]) => w.solution?.ready_to_fire && !w.reloading);
    const anyRailgunAmmo = railguns.some(([, w]) => (w.ammo ?? 0) > 0);

    if (this._authorized.railgun) {
      condRailgun.classList.add("visible");
      condRailgun.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "SOLUTION", met: anyRailgunReady },
        { label: "AMMO", met: anyRailgunAmmo },
      ]);
    } else {
      condRailgun.classList.remove("visible");
    }

    // -- Torpedo auth --
    const authTorpedoBtn = this.shadowRoot.getElementById("auth-torpedo");
    const condTorpedo = this.shadowRoot.getElementById("auth-cond-torpedo");
    authTorpedoBtn.classList.toggle("authorized", this._authorized.torpedo);
    authTorpedoBtn.querySelector(".auth-icon").textContent = this._authorized.torpedo ? "\u{1f513}" : "\u{1f512}";

    const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;
    const torpedoReady = torpedoCount > 0 && (torpedoData.cooldown ?? 0) <= 0;

    if (this._authorized.torpedo) {
      condTorpedo.classList.add("visible");
      condTorpedo.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "AMMO", met: torpedoCount > 0 },
        { label: "COOLDOWN", met: (torpedoData.cooldown ?? 0) <= 0, pending: (torpedoData.cooldown ?? 0) > 0 },
      ]);
    } else {
      condTorpedo.classList.remove("visible");
    }

    // -- Missile auth --
    const authMissileBtn = this.shadowRoot.getElementById("auth-missile");
    const condMissile = this.shadowRoot.getElementById("auth-cond-missile");
    authMissileBtn.classList.toggle("authorized", this._authorized.missile);
    authMissileBtn.querySelector(".auth-icon").textContent = this._authorized.missile ? "\u{1f513}" : "\u{1f512}";

    const missileCount = missileData.loaded ?? missileData.count ?? 0;
    const missileReady = missileCount > 0 && (missileData.cooldown ?? 0) <= 0;

    if (this._authorized.missile) {
      condMissile.classList.add("visible");
      condMissile.innerHTML = this._buildConditionsHtml([
        { label: "LOCK", met: hasLock },
        { label: "AMMO", met: missileCount > 0 },
        { label: "COOLDOWN", met: (missileData.cooldown ?? 0) <= 0, pending: (missileData.cooldown ?? 0) > 0 },
      ]);
    } else {
      condMissile.classList.remove("visible");
    }
  }

  /**
   * Build the HTML for a conditions checklist.
   * Each condition has {label, met, pending?}.
   */
  _buildConditionsHtml(conditions) {
    return conditions.map((c) => {
      let cls = c.met ? "met" : (c.pending ? "pending" : "unmet");
      let icon = c.met ? "\u2713" : (c.pending ? "\u23F3" : "\u2717");
      return `<span class="auth-cond ${cls}">${c.label} ${icon}</span>`;
    }).join("");
  }

  /**
   * Auto-execute queue: check each authorized weapon type and fire
   * when all conditions are satisfied. Runs every _updateDisplay tick.
   */
  _processAutoExecute(weapons, targeting, hasLock) {
    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};

    // --- Railgun auto-fire (continuous: stays authorized until manually de-authed) ---
    if (this._authorized.railgun && hasLock) {
      const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));
      for (const [mountId, w] of railguns) {
        const ammo = w.ammo ?? 0;
        const ready = w.solution?.ready_to_fire && ammo > 0 && !w.reloading;
        if (ready) {
          this._fireRailgun(mountId);
          this._showFireFlash("railgun");
          // Fire one mount per tick to avoid double-commanding the same mount
          break;
        }
      }
    }

    // --- Torpedo auto-fire (single shot, de-authorizes after firing) ---
    if (this._authorized.torpedo && hasLock) {
      const torpedoCount = torpedoData.loaded ?? torpedoData.count ?? 0;
      const torpedoReady = torpedoCount > 0 && (torpedoData.cooldown ?? 0) <= 0;
      if (torpedoReady) {
        this._fireLauncher();
        this._authorized.torpedo = false;
        this._showFireFlash("torpedo");
      }
    }

    // --- Missile auto-fire (fires configured salvo, de-authorizes after salvo) ---
    if (this._authorized.missile && hasLock && !this._salvoInProgress) {
      const missileCount = missileData.loaded ?? missileData.count ?? 0;
      const missileReady = missileCount > 0 && (missileData.cooldown ?? 0) <= 0;
      if (missileReady) {
        this._fireMissileSalvo();
        this._authorized.missile = false;
      }
    }
  }

  /**
   * Brief red/orange flash on the fire area to indicate auto-fire triggered.
   */
  _showFireFlash(type) {
    // Find the appropriate container to flash
    let target;
    if (type === "railgun") {
      target = this.shadowRoot.getElementById("railgun-mounts");
    } else {
      target = this.shadowRoot.getElementById("launcher-fire-row");
    }
    if (!target) return;

    // Ensure container is positioned for the absolute overlay
    const prevPosition = target.style.position;
    if (!prevPosition || prevPosition === "static") {
      target.style.position = "relative";
    }

    const flash = document.createElement("div");
    flash.className = "fire-flash-overlay" + (type === "missile" ? " missile" : "");
    target.appendChild(flash);

    // Remove after animation completes
    flash.addEventListener("animationend", () => {
      flash.remove();
      if (!prevPosition || prevPosition === "static") {
        target.style.position = prevPosition || "";
      }
    });
  }

  async _assessDamage() {
    try {
      const response = await wsClient.sendShipCommand("assess_damage", {});
      if (response && response.ok) {
        this._assessmentData = response;
        this._renderAssessment();
      }
    } catch (error) {
      console.error("Assess damage failed:", error);
    }
  }

  async _ceaseFire() {
    // De-authorize all weapons on cease fire
    this._authorized.railgun = false;
    this._authorized.torpedo = false;
    this._authorized.missile = false;

    try {
      await wsClient.sendShipCommand("set_pdc_mode", { mode: "hold_fire" });
    } catch (error) {
      console.error("Cease fire failed:", error);
    }
  }

  // --- Tier-specific display updates ---

  /**
   * ARCADE: update grouped fire buttons with confidence gate and ammo as percentage.
   * Button is disabled until confidence > 50% threshold.
   */
  _updateArcadeButtons(weapons, targeting, hasLock) {
    if (this._tier !== "arcade") return;

    const truthWeapons = weapons?.truth_weapons || {};
    const torpedoData = weapons?.torpedoes || weapons?.torpedo || {};
    const missileData = weapons?.missiles || {};
    const solutions = targeting?.solutions || {};

    // Best confidence across any weapon solution
    let bestConf = 0;
    for (const [, sol] of Object.entries(solutions)) {
      if ((sol.confidence ?? 0) > bestConf) bestConf = sol.confidence;
    }
    const confGate = hasLock && bestConf > 0.5;

    // Railgun: ammo as percentage
    const railguns = Object.entries(truthWeapons).filter(([id]) => id.startsWith("railgun"));
    let rgCurrent = 0, rgCapacity = 0;
    for (const [, w] of railguns) {
      rgCurrent += w.ammo ?? 0;
      rgCapacity += w.ammo_capacity ?? 0;
    }
    const rgPct = rgCapacity > 0 ? Math.round((rgCurrent / rgCapacity) * 100) : 0;
    const rgReady = railguns.some(([, w]) => w.solution?.ready_to_fire && !w.reloading && (w.ammo ?? 0) > 0);

    const rgBtn = this.shadowRoot.getElementById("arcade-fire-railgun");
    const rgAmmo = this.shadowRoot.getElementById("arcade-rg-ammo");
    if (rgBtn) rgBtn.disabled = !confGate || !rgReady;
    if (rgAmmo) rgAmmo.textContent = `${rgPct}%`;

    // Torpedo: ammo as percentage
    const trpLoaded = torpedoData.loaded ?? torpedoData.count ?? 0;
    const trpCapacity = torpedoData.capacity ?? trpLoaded;
    const trpPct = trpCapacity > 0 ? Math.round((trpLoaded / trpCapacity) * 100) : 0;
    const trpReady = trpLoaded > 0 && (torpedoData.cooldown ?? 0) <= 0;

    const trpBtn = this.shadowRoot.getElementById("arcade-fire-torpedo");
    const trpAmmo = this.shadowRoot.getElementById("arcade-trp-ammo");
    if (trpBtn) trpBtn.disabled = !confGate || !trpReady;
    if (trpAmmo) trpAmmo.textContent = `${trpPct}%`;

    // Missile: ammo as percentage
    const mslLoaded = missileData.loaded ?? missileData.count ?? 0;
    const mslCapacity = missileData.capacity ?? mslLoaded;
    const mslPct = mslCapacity > 0 ? Math.round((mslLoaded / mslCapacity) * 100) : 0;
    const mslReady = mslLoaded > 0 && (missileData.cooldown ?? 0) <= 0;

    const mslBtn = this.shadowRoot.getElementById("arcade-fire-missile");
    const mslAmmo = this.shadowRoot.getElementById("arcade-msl-ammo");
    if (mslBtn) mslBtn.disabled = !confGate || !mslReady;
    if (mslAmmo) mslAmmo.textContent = `${mslPct}%`;
  }

  /**
   * CPU-ASSIST: update per-weapon-type authorize card visuals.
   */
  _updateCpuAssistAuthCards() {
    if (this._tier !== "cpu-assist") return;

    for (const weapon of ["railgun", "torpedo", "missile"]) {
      const card = this.shadowRoot.getElementById(`cpuassist-auth-${weapon}`);
      if (!card) continue;
      const isAuth = this._authorized[weapon];
      card.classList.toggle("authorized", isAuth);
      const label = card.querySelector(".auth-toggle-label");
      if (label) label.textContent = isAuth ? "AUTHORIZED" : "AUTHORIZE";
    }
  }

  // --- Auto-Tactical (CPU-ASSIST tier) ---

  async _toggleAutoTactical() {
    const ship = stateManager.getShipState();
    const atState = ship?.auto_tactical;
    const enabled = atState?.enabled;

    try {
      if (enabled) {
        await wsClient.sendShipCommand("disable_auto_tactical", {});
      } else {
        await wsClient.sendShipCommand("enable_auto_tactical", {});
      }
    } catch (error) {
      console.error("Toggle auto-tactical failed:", error);
    }
  }

  _updateEngagementPanel() {
    const panel = this.shadowRoot.getElementById("engagement-panel");
    if (!panel) return;

    // Show only in CPU-ASSIST tier
    const tier = window.controlTier || "raw";
    panel.classList.toggle("visible", tier === "cpu-assist");

    if (tier !== "cpu-assist") return;

    const ship = stateManager.getShipState();
    const atState = ship?.auto_tactical;
    const enabled = atState?.enabled || false;
    const mode = atState?.engagement_mode || "weapons_free";
    const proposals = atState?.proposals || [];

    // Toggle button
    const toggle = this.shadowRoot.getElementById("engagement-toggle");
    toggle.textContent = enabled ? "DISABLE" : "ENABLE";
    toggle.classList.toggle("active", enabled);

    // Mode buttons
    this.shadowRoot.querySelectorAll(".engagement-mode-btn").forEach((btn) => {
      const isActive = btn.dataset.mode === mode;
      btn.classList.toggle("active", isActive);
      btn.classList.toggle("weapons-free", isActive && btn.dataset.mode === "weapons_free");
      btn.classList.toggle("defensive", isActive && btn.dataset.mode === "defensive_only");
    });

    // Proposals
    const container = this.shadowRoot.getElementById("tactical-proposals");
    if (!enabled || proposals.length === 0) {
      container.innerHTML = enabled
        ? '<div class="no-proposals">Scanning for targets...</div>'
        : '';
      return;
    }

    let html = '';
    for (const p of proposals) {
      const remaining = Math.max(0, p.time_remaining || 0);
      const total = p.total_time || 30;
      const timerPct = Math.min(100, (remaining / total) * 100);
      const actionLabel = p.action.replace(/_/g, " ").toUpperCase();
      const confidence = p.confidence ?? 0;
      const isUrgent = confidence > 0.8 || remaining < 5;
      const urgentClass = isUrgent ? " urgent" : "";
      const countdownClass = remaining < 5 ? " expiring" : "";
      html += `
        <div class="proposal-card${urgentClass}">
          <div class="proposal-header">
            <span class="proposal-action">${actionLabel} -- ${p.target_id || ""}</span>
            <span class="proposal-countdown${countdownClass}">${remaining.toFixed(1)}s</span>
          </div>
          <div class="proposal-reason">${p.reason}</div>
          <div class="proposal-timer"><div class="proposal-timer-fill" style="width:${timerPct}%"></div></div>
          <div class="proposal-actions">
            <button class="proposal-approve" data-id="${p.proposal_id}">APPROVE</button>
            <button class="proposal-deny" data-id="${p.proposal_id}">DENY</button>
          </div>
        </div>`;
    }
    container.innerHTML = html;
  }
}

customElements.define("weapon-controls", WeaponControls);
export { WeaponControls };
