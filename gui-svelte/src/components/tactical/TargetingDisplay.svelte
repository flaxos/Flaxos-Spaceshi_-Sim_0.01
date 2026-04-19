<script lang="ts">
  /**
   * TargetingDisplay — prototype-aligned lock/solution card.
   *
   * Sections (top → bottom):
   *   1. Lock state card: pulsing status dot + LOCKED/ACQUIRING/UNLOCKED text, track-quality %.
   *   2. Locked target block: target id/name + 6-cell k/v grid (Class, IFF, Distance, Bearing, Closure, Conf).
   *   3. Firing solution block: SVG circular arc gauge (stroke-dasharray = conf%) paired with TOF/TTI readouts.
   * Data wiring preserved: getTargetingSummary, getBestWeaponSolution, selectedTacticalTargetId,
   * lockTarget / unlockTarget actions. Solution polled every 2.5s via get_target_solution.
   */
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    asRecord,
    extractShipState,
    findTacticalContact,
    getBestWeaponSolution,
    getLockedTargetId,
    getTargetingSummary,
    toNumber,
    toStringValue,
    type TacticalContact,
  } from "./tacticalData.js";
  import { lockTarget, unlockTarget } from "./tacticalActions.js";

  let pollHandle: number | null = null;
  let solution: Record<string, unknown> = {};
  let locking = false;

  $: ship = extractShipState($gameState);
  $: targeting = getTargetingSummary(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: targetId = $selectedTacticalTargetId || lockedTargetId;
  $: contact = targetId ? findTacticalContact(ship, targetId) : null;
  $: bestSolution = getBestWeaponSolution(ship);

  // Prefer polled solution (freshest), fall back to tick-embedded solution.
  $: activeSolution = Object.keys(solution).length > 0 ? solution : bestSolution;
  $: confidence = clamp01(toNumber(activeSolution.confidence, targeting.lockQuality));
  $: confPct = Math.round(confidence * 100);
  $: trackQ = Math.round(targeting.trackQuality * 100);
  $: tof = toNumber(activeSolution.time_of_flight, NaN);
  $: tti = toNumber(activeSolution.time_to_cpa, toNumber(activeSolution.time_to_impact, NaN));

  onMount(() => {
    void refreshSolution();
    pollHandle = window.setInterval(() => void refreshSolution(), 2500);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refreshSolution() {
    if (!targetId) {
      solution = {};
      return;
    }
    try {
      const response = await wsClient.sendShipCommand("get_target_solution", {});
      solution = asRecord(response) ?? {};
    } catch {
      solution = {};
    }
  }

  async function lockSelectedTarget() {
    if (!targetId || locking) return;
    locking = true;
    try {
      await lockTarget(targetId);
      await refreshSolution();
    } finally {
      locking = false;
    }
  }

  async function clearTargetLock() {
    await unlockTarget();
    solution = {};
  }

  function clamp01(n: number): number {
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  function lockColor(state: string): string {
    switch (state) {
      case "locked":    return "var(--nom)";
      case "tracking":  return "var(--info)";
      case "acquiring": return "var(--warn)";
      case "designated": return "var(--warn)";
      default:          return "var(--tx-dim)";
    }
  }

  function lockBg(state: string): string {
    return state === "locked" ? "rgba(0, 221, 106, 0.05)" : "rgba(0, 0, 0, 0.18)";
  }

  function lockBorder(state: string): string {
    const col = lockColor(state);
    // Semi-transparent variant of state color
    if (col === "var(--nom)") return "rgba(0, 221, 106, 0.35)";
    if (col === "var(--info)") return "rgba(30, 140, 255, 0.35)";
    if (col === "var(--warn)") return "rgba(239, 160, 32, 0.35)";
    return "var(--bd-subtle)";
  }

  function confColor(pct: number): string {
    if (pct > 70) return "var(--nom)";
    if (pct > 45) return "var(--warn)";
    return "var(--crit)";
  }

  function iffTagFor(c: TacticalContact): string {
    const d = c.diplomaticState.toLowerCase();
    if (d.includes("hostile") || c.threatLevel === "red" || c.threatLevel === "orange") return "HOT";
    if (d.includes("friend") || d.includes("allied")) return "FRD";
    if (d.includes("unknown") || d === "") return "UNK";
    return "NEU";
  }

  function distStr(m: number): string {
    if (!Number.isFinite(m)) return "--";
    if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
    return `${Math.round(m)} m`;
  }

  // Arc gauge geometry — matches prototype: r=28, stroke=7, circumference≈175.9
  const ARC_R = 28;
  const ARC_CIRC = 2 * Math.PI * ARC_R; // ≈ 175.929
  $: arcDash = `${confidence * ARC_CIRC} ${ARC_CIRC}`;
</script>

<Panel
  title="Targeting Display"
  domain="weapons"
  priority={targeting.lockState === "locked" ? "primary" : "secondary"}
  className="targeting-display-panel"
>
  <div class="shell">
    <!-- Lock state header -->
    <div
      class="lock-card"
      style="background: {lockBg(targeting.lockState)}; border-color: {lockBorder(targeting.lockState)};"
    >
      <span
        class="lock-dot"
        class:pulsing={targeting.lockState === "acquiring" || targeting.lockState === "tracking"}
        class:locked={targeting.lockState === "locked"}
        style="background: {lockColor(targeting.lockState)};"
        aria-hidden="true"
      ></span>
      <div class="lock-main">
        <div class="field-label">Lock State</div>
        <div class="lock-state-txt" style="color: {lockColor(targeting.lockState)};">
          {targeting.lockState.toUpperCase()}
        </div>
      </div>
      <div class="lock-track">
        <div class="field-label">Track Q</div>
        <div class="lock-track-val" style="color: {trackQ > 75 ? 'var(--nom)' : 'var(--warn)'};">
          {trackQ}%
        </div>
      </div>
    </div>

    <!-- Locked target block -->
    {#if contact}
      <div class="block">
        <div class="divider">
          <span>Locked Target</span>
          <span class="divider-line"></span>
        </div>
        <div class="target-id">{contact.id} — {contact.name.toUpperCase()}</div>
        <div class="kv-grid">
          <div class="kv"><span>Class</span><strong>{contact.classification.toUpperCase()}</strong></div>
          <div class="kv"><span>IFF</span><strong>{iffTagFor(contact)}</strong></div>
          <div class="kv">
            <span>Distance</span>
            <strong>{distStr(contact.distance)}</strong>
          </div>
          <div class="kv">
            <span>Bearing</span>
            <strong>{String(Math.round(contact.bearing < 0 ? contact.bearing + 360 : contact.bearing)).padStart(3, "0")}°</strong>
          </div>
          <div class="kv">
            <span>Closure</span>
            <strong class:crit={Math.abs(contact.closureRate) > 150}>
              {(contact.closureRate > 0 ? "+" : "") + contact.closureRate.toFixed(1)} m/s
            </strong>
          </div>
          <div class="kv"><span>Conf.</span><strong>{Math.round(contact.confidence * 100)}%</strong></div>
        </div>
      </div>
    {:else}
      <div class="empty">No target designated.</div>
    {/if}

    <!-- Firing solution block -->
    {#if contact && (Object.keys(activeSolution).length > 0 || confidence > 0)}
      <div class="block">
        <div class="divider">
          <span>Firing Solution</span>
          <span class="divider-line"></span>
        </div>
        <div class="solution-row">
          <svg class="arc-gauge" width="68" height="68" viewBox="0 0 68 68">
            <circle cx="34" cy="34" r={ARC_R} fill="none" stroke="var(--bd-active)" stroke-width="7" />
            <circle
              cx="34"
              cy="34"
              r={ARC_R}
              fill="none"
              stroke={confColor(confPct)}
              stroke-width="7"
              stroke-linecap="round"
              stroke-dasharray={arcDash}
              transform="rotate(-90 34 34)"
              style="transition: stroke-dasharray 0.45s ease, stroke 0.4s ease;"
            />
            <text
              x="34"
              y="38"
              text-anchor="middle"
              font-size="13"
              font-weight="700"
              font-family="var(--font-mono)"
              fill={confColor(confPct)}
            >{confPct}%</text>
          </svg>
          <div class="sol-kvs">
            <div class="kv-lg">
              <span>Time of Flight</span>
              <strong>{Number.isFinite(tof) ? `${tof.toFixed(2)} s` : "—"}</strong>
            </div>
            <div class="kv-lg">
              <span>Time to Impact</span>
              <strong class:crit={Number.isFinite(tti) && tti < 10}>
                {Number.isFinite(tti) ? `${tti.toFixed(1)} s` : "—"}
              </strong>
            </div>
          </div>
        </div>
      </div>
    {/if}

    <!-- Actions -->
    <div class="actions">
      <button
        class="btn"
        disabled={!targetId || locking}
        title={!targetId ? "Select a contact first" : locking ? "Acquiring lock…" : "Acquire targeting lock"}
        on:click={lockSelectedTarget}
      >{locking ? "LOCKING…" : "LOCK TARGET"}</button>
      <button
        class="btn"
        disabled={!lockedTargetId}
        title={!lockedTargetId ? "No active lock" : "Release targeting lock"}
        on:click={clearTargetLock}
      >CLEAR LOCK</button>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 9px;
    padding: 10px;
    height: 100%;
    overflow-y: auto;
  }

  /* ── Lock state header ── */
  .lock-card {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 2px;
    border: 1px solid;
  }

  .lock-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .lock-dot.locked {
    box-shadow: 0 0 9px rgba(0, 221, 106, 0.7);
  }

  .lock-dot.pulsing {
    animation: pulse 1.2s ease-in-out infinite;
  }

  .lock-main {
    flex: 1;
    min-width: 0;
  }

  .lock-track {
    text-align: right;
  }

  .field-label {
    font-size: 0.52rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .lock-state-txt {
    font-size: 0.82rem;
    font-family: var(--font-mono);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .lock-track-val {
    font-size: 0.82rem;
    font-family: var(--font-mono);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  /* ── Target/solution block shell ── */
  .block {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .divider {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.52rem;
    font-family: var(--font-mono);
    color: var(--tx-dim);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .divider-line {
    flex: 1;
    height: 1px;
    background: var(--bd-subtle);
  }

  .target-id {
    font-size: 0.78rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: #ff8080;
    letter-spacing: 0.03em;
  }

  /* ── K/V grid (2 cols) ── */
  .kv-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5px 10px;
  }

  .kv {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .kv span {
    font-size: 0.5rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .kv strong {
    font-size: 0.66rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--tx-primary);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .kv strong.crit,
  .kv-lg strong.crit {
    color: var(--crit);
  }

  /* ── Firing solution row ── */
  .solution-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .arc-gauge {
    flex-shrink: 0;
  }

  .sol-kvs {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .kv-lg {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .kv-lg span {
    font-size: 0.52rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .kv-lg strong {
    font-size: 0.78rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--tx-primary);
    font-variant-numeric: tabular-nums;
  }

  /* ── Empty ── */
  .empty {
    padding: 18px 10px;
    text-align: center;
    font-size: var(--font-size-xs);
    color: var(--tx-dim);
    font-family: var(--font-mono);
    border: 1px dashed var(--bd-subtle);
    border-radius: 2px;
  }

  /* ── Actions ── */
  .actions {
    display: flex;
    gap: 6px;
    margin-top: auto;
  }

  .btn {
    flex: 1;
    padding: 6px 10px;
    background: transparent;
    border: 1px solid var(--bd-default);
    border-radius: 2px;
    color: var(--tx-sec);
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }

  .btn:hover:not(:disabled) {
    color: var(--tx-bright);
    border-color: var(--bd-focus);
  }

  .btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
