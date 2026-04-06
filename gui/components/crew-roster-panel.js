/**
 * Crew Roster Panel
 *
 * Displays full crew roster with:
 * - Name, assigned station, injury status indicator
 * - Skill levels with XP progress bars to next level
 * - "Level Up" notification when a skill advances
 *
 * Subscribes to stateManager for crew_progression telemetry.
 */

import { stateManager } from "../js/state-manager.js";

const SKILL_LEVEL_NAMES = {
  1: "NOVICE",
  2: "TRAINEE",
  3: "COMPETENT",
  4: "SKILLED",
  5: "EXPERT",
  6: "MASTER",
};

const SKILL_LEVEL_SHORT = {
  1: "NOV", 2: "TRN", 3: "CMP", 4: "SKL", 5: "EXP", 6: "MST",
};

const INJURY_INDICATORS = {
  healthy:  { icon: "\u25CF", color: "#00ff88", label: "Healthy" },
  wounded:  { icon: "\u25CF", color: "#ffaa00", label: "Wounded" },
  critical: { icon: "\u25CF", color: "#ff4444", label: "Critical" },
  dead:     { icon: "\u2620", color: "#666680", label: "KIA" },
};

// Skills grouped by station domain for cleaner display
const SKILL_GROUPS = [
  { label: "HELM",    skills: ["piloting", "navigation"] },
  { label: "COMBAT",  skills: ["gunnery", "targeting"] },
  { label: "OPS",     skills: ["sensors", "electronic_warfare"] },
  { label: "ENGRG",   skills: ["engineering", "damage_control"] },
  { label: "OTHER",   skills: ["communications", "command", "fleet_tactics"] },
];

class CrewRosterPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
    this._levelUpQueue = []; // Recent level-ups to flash
    this._prevLevels = {};   // crew_id -> { skill -> level } for detecting changes
  }

  connectedCallback() {
    this._renderShell();
    this._unsub = stateManager.subscribe("*", () => this._onState());
  }

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  _onState() {
    const state = stateManager.getState();
    const prog = state?.crew_progression;
    if (!prog || !prog.available) return;
    this._detectLevelUps(prog.roster || []);
    this._render(prog.roster || []);
  }

  _detectLevelUps(roster) {
    for (const crew of roster) {
      const prev = this._prevLevels[crew.crew_id] || {};
      const xpProg = crew.xp_progress || {};

      for (const [skill, info] of Object.entries(xpProg)) {
        const oldLevel = prev[skill] || 0;
        const newLevel = info.level || 0;
        if (oldLevel > 0 && newLevel > oldLevel) {
          this._levelUpQueue.push({
            name: crew.name,
            skill,
            level: newLevel,
            ts: Date.now(),
          });
        }
        prev[skill] = newLevel;
      }

      this._prevLevels[crew.crew_id] = prev;
    }
    // Expire old notifications (5 seconds)
    const now = Date.now();
    this._levelUpQueue = this._levelUpQueue.filter(n => now - n.ts < 5000);
  }

  _render(roster) {
    const container = this.shadowRoot.getElementById("roster-body");
    if (!container) return;

    if (!roster.length) {
      container.innerHTML = '<div class="empty">No crew assigned to this ship.</div>';
      return;
    }

    let html = "";

    // Level-up notifications
    if (this._levelUpQueue.length > 0) {
      html += '<div class="level-up-banner">';
      for (const n of this._levelUpQueue) {
        const lvName = SKILL_LEVEL_NAMES[n.level] || `L${n.level}`;
        html += `<div class="level-up-item">LEVEL UP: ${n.name} &mdash; ${n.skill} &rarr; ${lvName}</div>`;
      }
      html += "</div>";
    }

    for (const crew of roster) {
      html += this._renderCrewCard(crew);
    }

    container.innerHTML = html;
  }

  _renderCrewCard(crew) {
    const injury = INJURY_INDICATORS[crew.injury_state] || INJURY_INDICATORS.healthy;
    const station = crew.station_assignment || "UNASSIGNED";
    const xpProg = crew.xp_progress || {};

    let skillBars = "";
    for (const group of SKILL_GROUPS) {
      for (const skill of group.skills) {
        const info = xpProg[skill];
        if (!info) continue;
        const level = info.level || 1;
        const xp = info.xp || 0;
        const threshold = info.threshold;
        const pct = threshold ? Math.min(100, (xp / threshold) * 100) : 100;
        const lvShort = SKILL_LEVEL_SHORT[level] || `L${level}`;
        const isMax = level >= 6;

        skillBars += `
          <div class="skill-row">
            <span class="skill-name">${skill.replace("_", " ")}</span>
            <span class="skill-level">${lvShort}</span>
            <div class="xp-track">
              <div class="xp-fill ${isMax ? "max" : ""}" style="width:${pct.toFixed(0)}%"></div>
            </div>
            <span class="xp-label">${isMax ? "MAX" : `${xp}/${threshold}`}</span>
          </div>`;
      }
    }

    return `
      <div class="crew-card ${crew.injury_state === "dead" ? "dead" : ""}">
        <div class="card-header">
          <span class="injury-icon" style="color:${injury.color}" title="${injury.label}">${injury.icon}</span>
          <span class="crew-name">${crew.name}</span>
          <span class="station-badge">${station}</span>
        </div>
        <div class="status-row">
          <span class="stat">HP ${((crew.health || 0) * 100).toFixed(0)}%</span>
          <span class="stat">FAT ${((crew.fatigue || 0) * 100).toFixed(0)}%</span>
          <span class="stat">STR ${((crew.stress || 0) * 100).toFixed(0)}%</span>
          <span class="stat injury-label" style="color:${injury.color}">${injury.label.toUpperCase()}</span>
        </div>
        <div class="skills-section">
          ${skillBars}
        </div>
      </div>`;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--font-mono, "JetBrains Mono", monospace);
          font-size: 0.75rem;
          color: var(--text-primary, #e0e0e0);
          padding: 10px;
        }
        .empty {
          text-align: center;
          color: var(--text-dim, #666680);
          padding: 20px;
          font-style: italic;
        }
        .level-up-banner {
          margin-bottom: 10px;
          padding: 6px 10px;
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid #00ff88;
          border-radius: 4px;
          animation: flash 0.6s ease-in-out 3;
        }
        @keyframes flash {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .level-up-item {
          color: #00ff88;
          font-weight: 600;
          font-size: 0.8rem;
          padding: 2px 0;
        }
        .crew-card {
          background: var(--bg-input, #1a1a2e);
          border: 1px solid var(--border-default, #2a2a3a);
          border-radius: 6px;
          padding: 10px 12px;
          margin-bottom: 8px;
        }
        .crew-card.dead {
          opacity: 0.4;
          border-color: #ff4444;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .injury-icon { font-size: 0.9rem; }
        .crew-name { font-weight: 600; font-size: 0.85rem; flex: 1; }
        .station-badge {
          font-size: 0.6rem;
          padding: 2px 6px;
          border-radius: 3px;
          background: var(--status-info, #4488ff);
          color: #fff;
          text-transform: uppercase;
        }
        .status-row {
          display: flex;
          gap: 10px;
          margin-bottom: 8px;
          font-size: 0.65rem;
          color: var(--text-secondary, #a0a0b0);
        }
        .stat { white-space: nowrap; }
        .injury-label { font-weight: 600; }
        .skills-section {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .skill-row {
          display: flex;
          align-items: center;
          gap: 6px;
          height: 16px;
        }
        .skill-name {
          width: 100px;
          font-size: 0.6rem;
          color: var(--text-dim, #666680);
          text-transform: uppercase;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .skill-level {
          width: 26px;
          font-size: 0.6rem;
          font-weight: 600;
          color: var(--text-secondary, #a0a0b0);
          text-align: center;
        }
        .xp-track {
          flex: 1;
          height: 8px;
          background: rgba(0, 0, 0, 0.3);
          border-radius: 3px;
          overflow: hidden;
          min-width: 60px;
        }
        .xp-fill {
          height: 100%;
          background: var(--status-info, #4488ff);
          transition: width 0.3s ease;
          border-radius: 3px;
        }
        .xp-fill.max {
          background: var(--status-nominal, #00ff88);
        }
        .xp-label {
          width: 60px;
          font-size: 0.55rem;
          color: var(--text-dim, #666680);
          text-align: right;
          white-space: nowrap;
        }
      </style>
      <div id="roster-body">
        <div class="empty">Waiting for crew data...</div>
      </div>`;
  }
}

customElements.define("crew-roster-panel", CrewRosterPanel);
export { CrewRosterPanel };
