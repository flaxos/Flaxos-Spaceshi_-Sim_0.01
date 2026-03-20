/**
 * Shared autopilot utilities for flight-computer-panel and autopilot-status.
 * Extracted to keep both components under 300 lines.
 *
 * Provides:
 *  - Phase definitions per autopilot program
 *  - Phase progress HTML generation
 *  - Formatting helpers (distance, ETA, time)
 *  - State extraction from stateManager telemetry paths
 */

import { stateManager } from "./state-manager.js";

// Phase lists for different autopilot programs
const GOTO_PHASES = ["ACCELERATE", "COAST", "BRAKE", "HOLD"];
const RENDEZVOUS_PHASES = ["BURN", "FLIP", "BRAKE", "APPROACH_DECEL", "APPROACH_ROTATE", "APPROACH_COAST", "STATIONKEEP"];
const INTERCEPT_PHASES = ["INTERCEPT", "APPROACH", "MATCH"];

const PROGRAM_PHASES = {
  goto_position: GOTO_PHASES,
  set_course: GOTO_PHASES,
  rendezvous: RENDEZVOUS_PHASES,
  dock_approach: RENDEZVOUS_PHASES,
  intercept: INTERCEPT_PHASES,
};

const DEFAULT_PHASES = GOTO_PHASES;

const SHORT_PHASE_LABELS = {
  ACCELERATE: "Accel",
  COAST: "Coast",
  BRAKE: "Brake",
  HOLD: "Hold",
  BURN: "Burn",
  FLIP: "Flip",
  APPROACH_DECEL: "Decel",
  APPROACH_ROTATE: "Rotate",
  APPROACH_COAST: "Coast",
  STATIONKEEP: "Stnkeep",
  INTERCEPT: "Intrcpt",
  APPROACH: "Approach",
  MATCH: "Match",
};

/**
 * Get the phase list for a given program name.
 * @param {string|null} program - e.g. "rendezvous", "intercept", "goto_position"
 * @returns {string[]}
 */
function getPhasesForProgram(program) {
  const key = program?.toLowerCase() || "";
  return PROGRAM_PHASES[key] || DEFAULT_PHASES;
}

/**
 * Build phase progress bar HTML segments + labels.
 * Returns { segmentsHtml, labelsHtml } strings.
 * @param {string|null} program
 * @param {string|null} currentPhase - uppercase phase name
 */
function buildPhaseProgressHtml(program, currentPhase) {
  const phases = getPhasesForProgram(program);
  const idx = currentPhase ? phases.indexOf(currentPhase) : -1;

  const segmentsHtml = phases
    .map((p, i) => {
      let cls = `phase-segment ${p.toLowerCase()}`;
      if (i < idx) cls += " completed";
      else if (i === idx) cls += " active";
      return `<div class="${cls}" data-phase="${p}"></div>`;
    })
    .join("");

  const labelsHtml = phases
    .map((p, i) => {
      const active = i === idx ? " active" : "";
      const label = SHORT_PHASE_LABELS[p] || p;
      return `<span class="phase-label${active}" data-phase="${p}">${label}</span>`;
    })
    .join("");

  return { segmentsHtml, labelsHtml };
}

/**
 * CSS rules for phase segment coloring. Shared across components.
 * Inject into a <style> block.
 */
const PHASE_SEGMENT_CSS = `
  .phase-bar {
    display: flex;
    gap: 4px;
    margin-bottom: 4px;
  }
  .phase-segment {
    flex: 1;
    height: 6px;
    background: var(--bg-primary, #0a0a0f);
    border-radius: 3px;
    transition: background 0.3s ease;
  }
  .phase-segment.active { background: var(--status-info, #00aaff); }
  .phase-segment.completed { background: var(--status-nominal, #00ff88); }
  .phase-segment.accelerate.active { background: var(--status-warning, #ffaa00); }
  .phase-segment.coast.active { background: var(--status-info, #00aaff); }
  .phase-segment.brake.active { background: var(--status-critical, #ff4444); }
  .phase-segment.hold.active { background: var(--status-nominal, #00ff88); }
  .phase-segment.burn.active { background: var(--status-warning, #ffaa00); }
  .phase-segment.flip.active { background: #cc66ff; }
  .phase-segment.approach_decel.active { background: var(--status-critical, #ff4444); }
  .phase-segment.approach_rotate.active { background: #cc66ff; }
  .phase-segment.approach_coast.active { background: var(--status-info, #00aaff); }
  .phase-segment.stationkeep.active { background: var(--status-nominal, #00ff88); }
  .phase-segment.intercept.active { background: var(--status-warning, #ffaa00); }
  .phase-segment.approach.active { background: var(--status-info, #00aaff); }
  .phase-segment.match.active { background: var(--status-nominal, #00ff88); }
  .phase-labels {
    display: flex;
    justify-content: space-between;
  }
  .phase-label {
    font-size: 0.55rem;
    color: var(--text-dim, #555566);
    text-transform: uppercase;
  }
  .phase-label.active {
    color: var(--text-primary, #e0e0e0);
    font-weight: 600;
  }
`;

/** Format a distance in metres. Returns "X.X km" or "X m" or "--". */
function formatDistance(metres) {
  if (metres == null) return "--";
  if (metres >= 1000) return `${(metres / 1000).toFixed(1)} km`;
  return `${metres.toFixed(0)} m`;
}

/** Format seconds to human-readable ETA. */
function formatEta(seconds) {
  if (seconds == null || !isFinite(seconds)) return "--";
  if (seconds <= 0) return "0s";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m < 60) return `${m}m ${String(s).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${String(rm).padStart(2, "0")}m`;
}

/**
 * Extract a unified autopilot state object from stateManager.
 * Checks all known telemetry paths (top-level, station-filtered, systems).
 * Returns null when no autopilot is active.
 */
function extractAutopilotState() {
  const nav = stateManager.getNavigation();
  const ship = stateManager.getShipState();
  const ap = nav?.autopilot || ship?.autopilot || {};

  const mode =
    ap.mode || ship?.nav_mode || nav?.nav_mode || null;
  const program =
    ap.program || ship?.autopilot_program || nav?.current_program || null;

  // Rich autopilot state dict
  const apState =
    ship?.autopilot_state ||
    ap.autopilot_state ||
    ship?.systems?.navigation?.autopilot_state ||
    null;

  const phase = apState?.phase?.toUpperCase() || ap.phase?.toUpperCase() || null;

  const isActive =
    program ||
    (mode && mode !== "off" && mode !== "manual");

  if (!isActive) return null;

  return {
    mode: mode || "autopilot",
    program: program || mode,
    phase,
    target: ap.target || ap.course?.target || apState?.target || null,
    status: apState?.status || null,
    statusText: apState?.status_text || null,
    range: apState?.range ?? apState?.distance ?? null,
    closingSpeed: apState?.closing_speed ?? null,
    brakingDistance: apState?.braking_distance ?? null,
    eta: apState?.time_to_arrival ?? null,
    progress: ap.progress ?? null,
    burnPlan: ap.burn_plan ?? null,
    deltaV: ap.delta_v ?? apState?.delta_v ?? null,
  };
}

// Modes that should be hidden in CPU-ASSIST tier (too granular)
const CPU_ASSIST_HIDDEN_MODES = ["match", "orbit", "evasive", "hold_velocity"];

export {
  PROGRAM_PHASES,
  DEFAULT_PHASES,
  GOTO_PHASES,
  RENDEZVOUS_PHASES,
  INTERCEPT_PHASES,
  SHORT_PHASE_LABELS,
  PHASE_SEGMENT_CSS,
  CPU_ASSIST_HIDDEN_MODES,
  getPhasesForProgram,
  buildPhaseProgressHtml,
  formatDistance,
  formatEta,
  extractAutopilotState,
};
