/**
 * weapon-controls-styles.js
 * Shared CSS styles for the weapon controls component family.
 * Extracted from the monolithic weapon-controls.js to keep each
 * sub-component under 300 lines.
 *
 * Usage: import { getWeaponControlsCSS } from "./weapon-controls-styles.js";
 *        Then embed inside a <style> tag in your Shadow DOM template.
 */

/**
 * Returns the full CSS string for weapon control components.
 * Callers can pass a subset key to get only the styles they need,
 * or omit it to get everything.
 * @param {"all"|"railgun"|"pdc"|"launcher"|"authorization"|"shared"} [subset="all"]
 * @returns {string}
 */
export function getWeaponControlsCSS(subset = "all") {
  const sections = {
    shared: SHARED_CSS,
    railgun: RAILGUN_CSS,
    pdc: PDC_CSS,
    launcher: LAUNCHER_CSS,
    authorization: AUTHORIZATION_CSS,
    tier: TIER_CSS,
    engagement: ENGAGEMENT_CSS,
    assessment: ASSESSMENT_CSS,
    ammo: AMMO_HEAT_CSS,
  };

  if (subset === "all") {
    return Object.values(sections).join("\n");
  }
  return (sections[subset] || "") + "\n" + SHARED_CSS;
}

// ---------------------------------------------------------------------------
// SHARED — base layout, weapon-group, fire-btn, warning, cease-fire
// ---------------------------------------------------------------------------
const SHARED_CSS = `
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

  /* === Tier-specific visibility classes === */
  .tier-hidden { display: none !important; }
`;

// ---------------------------------------------------------------------------
// RAILGUN — mount row, charge state, fire buttons
// ---------------------------------------------------------------------------
const RAILGUN_CSS = `
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
`;

// ---------------------------------------------------------------------------
// PDC — mode selector, threat list
// ---------------------------------------------------------------------------
const PDC_CSS = `
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

  /* PDC Threat List (visible in PRIORITY mode) */
  .pdc-threat-list {
    margin-top: 6px;
    padding: 6px 8px;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 80, 80, 0.25);
    border-radius: 6px;
  }

  .threat-list-header {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--status-critical, #ff4444);
    margin-bottom: 4px;
    text-transform: uppercase;
  }

  .threat-list-items {
    display: flex;
    flex-direction: column;
    gap: 3px;
    max-height: 120px;
    overflow-y: auto;
  }

  .threat-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 4px;
    font-size: 0.65rem;
    cursor: pointer;
    transition: background 0.1s ease;
  }

  .threat-item:hover {
    background: rgba(255, 80, 80, 0.1);
    border-color: rgba(255, 80, 80, 0.3);
  }

  .threat-item.prioritized {
    border-color: rgba(255, 170, 0, 0.4);
    background: rgba(255, 170, 0, 0.08);
  }

  .threat-priority-num {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--status-warning, #ffaa00);
    color: #000;
    font-size: 0.55rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .threat-type {
    font-weight: 600;
    text-transform: uppercase;
    flex-shrink: 0;
  }

  .threat-type.torpedo { color: #ff4444; }
  .threat-type.missile { color: #ff8800; }

  .threat-range {
    color: var(--text-dim, #888);
    margin-left: auto;
  }

  .threat-eta {
    color: var(--status-warning, #ffaa00);
    font-weight: 600;
    min-width: 40px;
    text-align: right;
  }

  .threat-empty {
    font-size: 0.6rem;
    color: var(--text-dim, #555);
    font-style: italic;
    padding: 4px 0;
  }
`;

// ---------------------------------------------------------------------------
// LAUNCHER — torpedo/missile toggle, salvo selector, flight profile
// ---------------------------------------------------------------------------
const LAUNCHER_CSS = `
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

  /* Launcher Type Selector -- styled like PDC mode toggle */
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

  /* Salvo/profile controls only visible when missile type is selected */
  .missile-options {
    display: none;
  }

  .missile-options.visible {
    display: block;
  }
`;

// ---------------------------------------------------------------------------
// AUTHORIZATION — auth buttons, conditions checklist
// ---------------------------------------------------------------------------
const AUTHORIZATION_CSS = `
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
`;

// ---------------------------------------------------------------------------
// TIER — manual, arcade, cpu-assist visibility rules
// ---------------------------------------------------------------------------
const TIER_CSS = `
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
`;

// ---------------------------------------------------------------------------
// ENGAGEMENT — auto-tactical panel (CPU-ASSIST)
// ---------------------------------------------------------------------------
const ENGAGEMENT_CSS = `
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
`;

// ---------------------------------------------------------------------------
// ASSESSMENT — damage assessment results
// ---------------------------------------------------------------------------
const ASSESSMENT_CSS = `
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
`;

// ---------------------------------------------------------------------------
// AMMO / HEAT HUD
// ---------------------------------------------------------------------------
const AMMO_HEAT_CSS = `
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
`;
