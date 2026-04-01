/**
 * After-Action Report Component
 *
 * Displays a comprehensive mission score breakdown after completion.
 * Score axes: efficiency, accuracy, preservation, crew_safety, objectives.
 * Style bonuses: SURGICAL, UNTOUCHABLE, KNIFE EDGE, AMMO MISER.
 * Debrief section with 3 improvement tips from combat log analysis.
 *
 * Triggered by the mission_complete event or by calling show(scoreData).
 */

import { wsClient } from "../js/ws-client.js";

const GRADE_COLORS = {
  S: "#ffdd00",
  A: "#00ff88",
  B: "#00aaff",
  C: "#ffaa00",
  D: "#ff6644",
  F: "#ff2222",
};

const BADGE_LABELS = {
  surgical: "SURGICAL",
  untouchable: "UNTOUCHABLE",
  knife_edge: "KNIFE EDGE",
  ammo_miser: "AMMO MISER",
};

const BADGE_DESCRIPTIONS = {
  surgical: "Mission kill without hull destruction",
  untouchable: "Zero damage taken",
  knife_edge: "Completed with < 25% fuel remaining",
  ammo_miser: "Completed with > 75% ammo remaining",
};

class AfterActionReport extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scoreData = null;
  }

  connectedCallback() {
    this._render();
  }

  /**
   * Show the after-action report with the given score data.
   * @param {object} scoreData - MissionScore.to_dict() payload
   */
  show(scoreData) {
    this._scoreData = scoreData;
    this._render();
    this.style.display = "block";
  }

  /** Hide the report. */
  hide() {
    this.style.display = "none";
    this._scoreData = null;
  }

  /**
   * Fetch score from server and display.
   * Useful when the event payload didn't include the score.
   */
  async fetchAndShow() {
    try {
      const resp = await wsClient.send("get_mission_score", {});
      if (resp?.ok && resp.score && resp.score.grade) {
        this.show(resp.score);
      }
    } catch (err) {
      console.warn("Failed to fetch mission score:", err);
    }
  }

  _render() {
    const s = this._scoreData;
    if (!s) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const gradeColor = GRADE_COLORS[s.grade] || "#888899";
    const isSuccess = s.mission_result === "success";
    const resultLabel = isSuccess ? "MISSION COMPLETE" : "MISSION FAILED";
    const resultColor = isSuccess ? "#00ff88" : "#ff4444";

    // Build metric bars
    const metrics = [
      { key: "efficiency", label: "EFFICIENCY", value: s.efficiency },
      { key: "accuracy", label: "ACCURACY", value: s.accuracy },
      { key: "preservation", label: "PRESERVATION", value: s.preservation },
      { key: "crew_safety", label: "CREW SAFETY", value: s.crew_safety },
      { key: "objectives", label: "OBJECTIVES", value: s.objectives },
    ];

    const metricBarsHtml = metrics.map(m => {
      const pct = Math.min(100, Math.round((m.value || 0) * 100));
      const barColor = pct >= 75 ? "#00ff88" : pct >= 50 ? "#ffaa00" : "#ff4444";
      return `
        <div class="aar-metric">
          <span class="aar-metric-label">${m.label}</span>
          <div class="aar-bar-track">
            <div class="aar-bar-fill" style="width: ${pct}%; background: ${barColor};"></div>
          </div>
          <span class="aar-metric-value">${pct}%</span>
        </div>
      `;
    }).join("");

    // Build style badges
    const badges = Object.keys(BADGE_LABELS)
      .filter(k => s[k])
      .map(k => `<span class="aar-badge" title="${BADGE_DESCRIPTIONS[k]}">${BADGE_LABELS[k]}</span>`)
      .join("");

    // Build improvement tips
    const tipsHtml = (s.improvement_tips || []).map((tip, i) => `
      <div class="aar-tip">
        <span class="aar-tip-number">${i + 1}</span>
        <span class="aar-tip-text">${tip}</span>
      </div>
    `).join("") || '<div class="aar-tip"><span class="aar-tip-text">No specific tips -- good flying.</span></div>';

    // Build combat stats summary
    const statsHtml = `
      <div class="aar-stats-grid">
        <div class="aar-stat"><span class="aar-stat-label">Shots Fired</span><span class="aar-stat-value">${s.shots_fired || 0}</span></div>
        <div class="aar-stat"><span class="aar-stat-label">Shots Hit</span><span class="aar-stat-value">${s.shots_hit || 0}</span></div>
        <div class="aar-stat"><span class="aar-stat-label">Torpedoes</span><span class="aar-stat-value">${s.torpedoes_hit || 0}/${s.torpedoes_launched || 0}</span></div>
        <div class="aar-stat"><span class="aar-stat-label">Missiles</span><span class="aar-stat-value">${s.missiles_hit || 0}/${s.missiles_launched || 0}</span></div>
        <div class="aar-stat"><span class="aar-stat-label">Damage Dealt</span><span class="aar-stat-value">${(s.damage_dealt || 0).toFixed(0)}</span></div>
        <div class="aar-stat"><span class="aar-stat-label">Damage Taken</span><span class="aar-stat-value">${(s.damage_taken || 0).toFixed(0)}</span></div>
      </div>
    `;

    // Build timeline
    const timelineHtml = (s.timeline || []).map(ev => {
      const sevColor = {
        hit: "#00ff88", miss: "#888899", damage: "#ffaa00", critical: "#ff4444", info: "#00aaff",
      }[ev.severity] || "#888899";
      const timeStr = ev.time != null ? `${ev.time.toFixed(1)}s` : "";
      return `
        <div class="aar-timeline-event">
          <span class="aar-tl-time">${timeStr}</span>
          <span class="aar-tl-dot" style="background: ${sevColor};"></span>
          <span class="aar-tl-summary">${ev.summary || ev.type}</span>
        </div>
      `;
    }).join("") || '<div class="aar-timeline-event"><span class="aar-tl-summary">No combat events recorded.</span></div>';

    this.shadowRoot.innerHTML = `
      <style>${this._styles(gradeColor, resultColor)}</style>
      <div class="aar-container">
        <div class="aar-header">
          <div class="aar-result" style="color: ${resultColor};">${resultLabel}</div>
          <div class="aar-grade-box">
            <div class="aar-grade" style="color: ${gradeColor}; text-shadow: 0 0 20px ${gradeColor}40;">${s.grade}</div>
            <div class="aar-score">${s.total_score} / 1000</div>
          </div>
        </div>

        ${badges ? `<div class="aar-badges">${badges}</div>` : ""}

        <div class="aar-section">
          <h3 class="aar-section-title">PERFORMANCE</h3>
          ${metricBarsHtml}
        </div>

        <div class="aar-section">
          <h3 class="aar-section-title">COMBAT STATS</h3>
          ${statsHtml}
        </div>

        <div class="aar-section">
          <h3 class="aar-section-title">DEBRIEF</h3>
          ${tipsHtml}
        </div>

        <div class="aar-section aar-timeline-section">
          <h3 class="aar-section-title">TIMELINE</h3>
          <div class="aar-timeline">${timelineHtml}</div>
        </div>
      </div>
    `;
  }

  _styles(gradeColor, resultColor) {
    return `
      :host {
        display: none;
      }
      .aar-container {
        font-family: var(--font-sans, "Inter", sans-serif);
        color: var(--text-primary, #e0e0e0);
        background: var(--bg-panel, #12121a);
        border: 1px solid var(--border-default, #2a2a3a);
        border-radius: 8px;
        padding: 20px;
        max-height: 70vh;
        overflow-y: auto;
      }
      .aar-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--border-default, #2a2a3a);
      }
      .aar-result {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 1rem;
        font-weight: 700;
        letter-spacing: 0.12em;
      }
      .aar-grade-box {
        text-align: center;
      }
      .aar-grade {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 2.5rem;
        font-weight: 900;
        line-height: 1;
      }
      .aar-score {
        font-size: 0.75rem;
        color: var(--text-secondary, #888899);
        margin-top: 2px;
      }
      .aar-badges {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 16px;
      }
      .aar-badge {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        padding: 4px 10px;
        border-radius: 4px;
        background: rgba(255, 221, 0, 0.1);
        border: 1px solid rgba(255, 221, 0, 0.4);
        color: #ffdd00;
        cursor: default;
      }
      .aar-section {
        margin-bottom: 16px;
      }
      .aar-section-title {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.15em;
        color: var(--text-dim, #555566);
        margin: 0 0 10px 0;
        text-transform: uppercase;
      }
      .aar-metric {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
      }
      .aar-metric-label {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        color: var(--text-secondary, #888899);
        width: 110px;
        flex-shrink: 0;
        letter-spacing: 0.05em;
      }
      .aar-bar-track {
        flex: 1;
        height: 8px;
        background: var(--bg-input, #1a1a24);
        border-radius: 4px;
        overflow: hidden;
      }
      .aar-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.6s ease;
      }
      .aar-metric-value {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        width: 36px;
        text-align: right;
        color: var(--text-primary, #e0e0e0);
      }
      .aar-stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 8px;
      }
      .aar-stat {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .aar-stat-label {
        font-size: 0.65rem;
        color: var(--text-dim, #555566);
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .aar-stat-value {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.85rem;
        color: var(--text-primary, #e0e0e0);
      }
      .aar-tip {
        display: flex;
        gap: 10px;
        margin-bottom: 8px;
        align-items: flex-start;
      }
      .aar-tip-number {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        font-size: 0.7rem;
        font-weight: 700;
        color: #ffaa00;
        width: 16px;
        flex-shrink: 0;
        text-align: center;
      }
      .aar-tip-text {
        font-size: 0.8rem;
        line-height: 1.5;
        color: var(--text-primary, #e0e0e0);
      }
      .aar-timeline-section {
        max-height: 200px;
        overflow-y: auto;
      }
      .aar-timeline {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .aar-timeline-event {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.7rem;
      }
      .aar-tl-time {
        font-family: var(--font-mono, "JetBrains Mono", monospace);
        color: var(--text-dim, #555566);
        width: 50px;
        text-align: right;
        flex-shrink: 0;
      }
      .aar-tl-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        flex-shrink: 0;
      }
      .aar-tl-summary {
        color: var(--text-secondary, #888899);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    `;
  }
}

customElements.define("after-action-report", AfterActionReport);
export default AfterActionReport;
