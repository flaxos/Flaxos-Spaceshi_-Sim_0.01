/**
 * nav-phase-strip — compact embeddable autopilot phase progress strip.
 *
 * Shows: program badge | phase segments bar | labels | status line.
 * Hides itself when no AP is active or when program has no phases.
 *
 * Designed to embed in any view (tactical, ops) so the operator can
 * monitor autopilot state without switching to the helm view.
 */

import { stateManager } from "../js/state-manager.js";
import {
  extractAutopilotState,
  buildPhaseProgressHtml,
  PHASE_SEGMENT_CSS,
  formatDistance,
  formatEta,
} from "../js/autopilot-utils.js";

class NavPhaseStrip extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._unsub = null;
  }

  connectedCallback() {
    this._render();
    this._unsub = stateManager.subscribe("*", () => this._update());
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  _render() {
    this.shadowRoot.innerHTML = `<style>
:host { display: block; }
:host([hidden]) { display: none; }
.strip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-secondary, #12121a);
  border-bottom: 1px solid var(--border-default, #2a2a3a);
  font-family: var(--font-sans, "Inter", sans-serif);
}
.top-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.prog-badge {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.6rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--bg-input, #1a1a24);
  color: var(--text-secondary, #888899);
  text-transform: uppercase;
  letter-spacing: 1px;
  white-space: nowrap;
  flex-shrink: 0;
}
.prog-badge.active {
  background: rgba(0,170,255,.15);
  color: var(--status-info, #00aaff);
}
.phase-area { flex: 1; min-width: 0; }
${PHASE_SEGMENT_CSS}
.phase-bar { margin-bottom: 2px; }
.phase-labels { font-size: 0.5rem; }
.status-line {
  font-size: 0.65rem;
  color: var(--text-secondary, #888899);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.flip-soon { color: var(--status-warning, #ffaa00); font-weight: 600; }
</style>
<div class="strip" id="strip" style="display:none">
  <div class="top-row">
    <span class="prog-badge" id="prog-badge">--</span>
    <div class="phase-area">
      <div class="phase-bar" id="phase-bar"></div>
      <div class="phase-labels" id="phase-labels"></div>
    </div>
  </div>
  <div class="status-line" id="status-line"></div>
</div>`;
  }

  _update() {
    const ap = extractAutopilotState();
    const strip = this.shadowRoot.getElementById("strip");
    if (!ap) { strip.style.display = "none"; return; }
    strip.style.display = "";

    // Program badge
    const badge = this.shadowRoot.getElementById("prog-badge");
    badge.textContent = (ap.program || "AP").toUpperCase().replace(/_/g, " ");
    badge.className = "prog-badge active";

    // Phase bar + labels
    const { segmentsHtml, labelsHtml } = buildPhaseProgressHtml(ap.program, ap.phase);
    this.shadowRoot.getElementById("phase-bar").innerHTML = segmentsHtml;
    this.shadowRoot.getElementById("phase-labels").innerHTML = labelsHtml;

    // Status line: flip countdown in BURN, else status text / ETA
    const statusEl = this.shadowRoot.getElementById("status-line");
    const phase = (ap.phase || "").toLowerCase();
    if (phase === "burn" && ap.flipInM != null) {
      const dist = formatDistance(ap.flipInM);
      const t = formatEta(ap.flipInS);
      statusEl.innerHTML = `Flip in: <span class="flip-soon">${dist} / ~${t}</span>${ap.eta != null ? ` &nbsp;·&nbsp; ETA ${formatEta(ap.eta)}` : ""}`;
    } else if (ap.statusText) {
      statusEl.textContent = ap.statusText;
    } else if (ap.eta != null) {
      statusEl.textContent = `ETA ${formatEta(ap.eta)}`;
    } else {
      statusEl.textContent = "";
    }
  }
}

customElements.define("nav-phase-strip", NavPhaseStrip);
export { NavPhaseStrip };
