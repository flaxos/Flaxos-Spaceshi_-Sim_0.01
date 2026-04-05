/**
 * proposal-styles.js — Shared CSS for CPU-ASSIST proposal cards.
 *
 * Since all components use Shadow DOM, external stylesheets don't
 * penetrate the shadow boundary. This module fetches the shared
 * proposals.css at import time and exposes it as a string that
 * components inject into their shadow <style> blocks.
 *
 * Usage in a component:
 *   import { proposalCSS } from "../js/proposal-styles.js";
 *   // then in render():  `<style>${proposalCSS}</style>`
 */

let _cachedCSS = "";
let _fetchPromise = null;

/**
 * Fetch proposals.css once and cache the result.
 * Returns a promise that resolves to the CSS string.
 */
function _loadCSS() {
  if (_cachedCSS) return Promise.resolve(_cachedCSS);
  if (_fetchPromise) return _fetchPromise;

  _fetchPromise = fetch(new URL("../styles/proposals.css", import.meta.url))
    .then(r => {
      if (!r.ok) throw new Error(`Failed to load proposals.css: ${r.status}`);
      return r.text();
    })
    .then(css => {
      _cachedCSS = css;
      return css;
    })
    .catch(err => {
      console.warn("[proposal-styles] Could not load proposals.css, using inline fallback:", err);
      // Minimal inline fallback so the UI is never broken
      _cachedCSS = INLINE_FALLBACK;
      return _cachedCSS;
    });

  return _fetchPromise;
}

// Kick off the fetch immediately on import so it's ready by the time
// components render.  The CSS file is small (~3KB).
_loadCSS();

/**
 * The proposal CSS string. Components should access this synchronously.
 * If the fetch hasn't completed yet (very unlikely on a local server),
 * the inline fallback is returned.
 */
export function getProposalCSS() {
  return _cachedCSS || INLINE_FALLBACK;
}

// For synchronous import convenience — most components render after
// the first state update, by which time the fetch has long completed.
// This getter re-exports the same value.
export { _cachedCSS as proposalCSS };

// Re-export the load promise for components that want to await it
// before first render (optional).
export const proposalCSSReady = _loadCSS();

/* -------------------------------------------------------------------------
   INLINE FALLBACK — minimal version of proposals.css
   Used only if the fetch fails (e.g., running from file:// protocol).
   ------------------------------------------------------------------------- */

const INLINE_FALLBACK = `
.proposal-card {
  background: rgba(192, 160, 255, 0.06);
  border: 1px solid rgba(192, 160, 255, 0.3);
  border-left: 3px solid var(--tier-accent, #c0a0ff);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  animation: proposalSlideIn 0.3s ease-out;
  position: relative;
  overflow: hidden;
}
.proposal-card.urgent {
  border-color: var(--status-warning, #ffaa00);
  border-left-color: var(--status-warning, #ffaa00);
  background: rgba(255, 170, 0, 0.08);
  animation: proposalSlideIn 0.3s ease-out, proposalPulse 2s ease-in-out 0.3s infinite;
}
.proposal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.proposal-action {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--tier-accent, #c0a0ff);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.proposal-card.urgent .proposal-action {
  color: var(--status-warning, #ffaa00);
}
.proposal-confidence {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--status-nominal, #00ff88);
  background: rgba(0, 255, 136, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
}
.proposal-countdown {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.7rem;
  color: var(--text-dim, #555566);
}
.proposal-countdown.expiring {
  color: var(--status-warning, #ffaa00);
  font-weight: 700;
}
.proposal-reason, .proposal-desc {
  font-size: 0.72rem;
  color: var(--text-secondary, #888899);
  line-height: 1.4;
  margin-bottom: 8px;
}
.proposal-timer {
  height: 3px;
  background: rgba(192, 160, 255, 0.1);
  border-radius: 2px;
  margin-bottom: 8px;
  overflow: hidden;
}
.proposal-timer-fill {
  height: 100%;
  background: var(--tier-accent, #c0a0ff);
  border-radius: 2px;
  transition: width 1s linear;
}
.proposal-card.urgent .proposal-timer-fill {
  background: var(--status-warning, #ffaa00);
}
.proposal-actions {
  display: flex;
  gap: 6px;
}
.proposal-approve, .btn-approve {
  flex: 1;
  padding: 6px 10px;
  background: rgba(0, 255, 136, 0.1);
  border: 1px solid rgba(0, 255, 136, 0.4);
  border-radius: 4px;
  color: var(--status-nominal, #00ff88);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.7rem;
  font-weight: 700;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  transition: all 0.15s ease;
}
.proposal-approve:hover, .btn-approve:hover {
  background: rgba(0, 255, 136, 0.2);
  border-color: var(--status-nominal, #00ff88);
  box-shadow: 0 0 8px rgba(0, 255, 136, 0.15);
}
.proposal-deny, .btn-deny {
  flex: 1;
  padding: 6px 10px;
  background: rgba(255, 68, 68, 0.1);
  border: 1px solid rgba(255, 68, 68, 0.4);
  border-radius: 4px;
  color: var(--status-critical, #ff4444);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 0.7rem;
  font-weight: 700;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  transition: all 0.15s ease;
}
.proposal-deny:hover, .btn-deny:hover {
  background: rgba(255, 68, 68, 0.2);
  border-color: var(--status-critical, #ff4444);
  box-shadow: 0 0 8px rgba(255, 68, 68, 0.15);
}
.no-proposals {
  font-size: 0.7rem;
  color: var(--text-dim, #555566);
  font-style: italic;
  text-align: center;
  padding: 12px 8px;
}
.proposals-container, .proposals-queue, .proposals {
  display: flex;
  flex-direction: column;
  gap: 0;
  max-height: 400px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(192, 160, 255, 0.2) transparent;
}
@keyframes proposalSlideIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes proposalPulse {
  0%, 100% { border-color: rgba(192, 160, 255, 0.3); box-shadow: none; }
  50% { border-color: var(--status-warning, #ffaa00); box-shadow: 0 0 12px rgba(255,170,0,0.2); }
}
@media (prefers-reduced-motion: reduce) {
  .proposal-card { animation: none; }
  .proposal-card.urgent { animation: none; box-shadow: 0 0 8px rgba(255,170,0,0.15); }
  .proposal-approve, .proposal-deny, .btn-approve, .btn-deny { transition: none; }
  .proposal-timer-fill { transition: none; }
}
`;
