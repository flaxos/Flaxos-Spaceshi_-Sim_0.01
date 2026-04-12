<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { selectedHelmTargetId } from "../../lib/stores/helmUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    asRecord,
    extractShipState,
    formatDistance,
    formatDuration,
    getAutopilotSnapshot,
    getContacts,
    toNumber,
    toStringValue,
  } from "./helmData.js";

  type ProfileName = "aggressive" | "balanced" | "conservative";
  type CommandName = "rendezvous" | "intercept" | "match" | "hold";

  interface SolutionCard {
    profile: ProfileName;
    totalTime: number;
    fuelCost: number;
    accuracy: number;
    riskLevel: string;
    description: string;
    maxThrust: number;
    estimatedFlipTime: number;
  }

  let profile: ProfileName = "balanced";
  let xInput = "";
  let yInput = "";
  let zInput = "";
  let vxInput = "";
  let vyInput = "";
  let vzInput = "";
  let navSolutions: SolutionCard[] = [];
  let busy = false;
  let navBusy = false;
  let feedback = "";
  let pollHandle: number | null = null;

  $: ship = extractShipState($gameState);
  $: contacts = getContacts(ship);
  $: shipTargetId = toStringValue(ship.target_id);
  $: activeTargetId = $selectedHelmTargetId || shipTargetId;
  $: autopilot = getAutopilotSnapshot(ship);
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
  $: rawTier = $tier === "raw";
  $: hasCoords = [xInput, yInput, zInput].every((value) => value.trim() !== "");
  $: canSolve = Boolean(activeTargetId || hasCoords);
  $: recommended = pickRecommended(navSolutions);

  onMount(() => {
    void refreshSolutions();
    pollHandle = window.setInterval(() => {
      if (canSolve && (rawTier || cpuAssistTier)) void refreshSolutions();
    }, 5000);

    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  function toSolutionCards(source: unknown): SolutionCard[] {
    const solutions = asRecord(asRecord(source)?.solutions);
    if (!solutions) return [];

    return (Object.entries(solutions) as [string, unknown][])
      .map(([name, value]) => {
        const row = asRecord(value);
        if (!row) return null;
        return {
          profile: (name as ProfileName),
          totalTime: toNumber(row.total_time),
          fuelCost: toNumber(row.fuel_cost),
          accuracy: toNumber(row.accuracy),
          riskLevel: toStringValue(row.risk_level, "medium"),
          description: toStringValue(row.description),
          maxThrust: toNumber(row.max_thrust),
          estimatedFlipTime: toNumber(row.estimated_flip_time),
        };
      })
      .filter((row): row is SolutionCard => Boolean(row));
  }

  function pickRecommended(solutions: SolutionCard[]): SolutionCard | null {
    if (solutions.length === 0) return null;
    const penalties: Record<string, number> = { low: 0.08, medium: 0.2, high: 0.38 };
    const sorted = [...solutions].sort((a, b) => {
      const scoreA = a.fuelCost + a.totalTime / 10_000 + (penalties[a.riskLevel] ?? 0.2);
      const scoreB = b.fuelCost + b.totalTime / 10_000 + (penalties[b.riskLevel] ?? 0.2);
      return scoreA - scoreB;
    });
    return sorted[0];
  }

  async function refreshSolutions() {
    if (!canSolve) {
      navSolutions = [];
      return;
    }

    navBusy = true;
    try {
      const params = activeTargetId
        ? { target_id: activeTargetId }
        : { x: Number(xInput), y: Number(yInput), z: Number(zInput) };
      const response = await wsClient.sendShipCommand("get_nav_solutions", params);
      navSolutions = toSolutionCards(response);
    } catch {
      navSolutions = [];
    } finally {
      navBusy = false;
    }
  }

  async function engageCommand(program: CommandName) {
    busy = true;
    feedback = "";

    try {
      if (program === "hold") {
        await wsClient.sendShipCommand("autopilot", { enable: true, program: "hold" });
        feedback = "Hold position engaged";
      } else {
        if (!activeTargetId) {
          feedback = "Select a target first";
          return;
        }

        await wsClient.sendShipCommand("autopilot", {
          enable: true,
          program,
          target: activeTargetId,
          profile,
        });
        feedback = `${program.toUpperCase()} engaged`;
      }
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Flight computer command failed";
    } finally {
      busy = false;
    }
  }

  async function setCourse() {
    if (!hasCoords) {
      feedback = "Enter X/Y/Z coordinates";
      return;
    }

    busy = true;
    feedback = "";

    try {
      await wsClient.sendShipCommand("set_course", {
        x: Number(xInput),
        y: Number(yInput),
        z: Number(zInput),
        stop: true,
        profile,
      });
      feedback = "Course uploaded";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Course upload failed";
    } finally {
      busy = false;
    }
  }

  async function approveRecommended() {
    if (activeTargetId) {
      await engageCommand("rendezvous");
      return;
    }

    await setCourse();
  }

  function onTargetChange(event: Event) {
    const target = event.currentTarget as HTMLSelectElement;
    selectedHelmTargetId.set(target.value);
    void refreshSolutions();
  }

  function onCoordinateBlur() {
    void refreshSolutions();
  }
</script>

<Panel title="Flight Computer" domain="helm" priority={arcadeTier || cpuAssistTier ? "primary" : "secondary"} className="flight-computer-panel">
  <div class="content">
    {#if !arcadeTier}
      <div class="selector-row">
        <label>
          Target
          <select on:change={onTargetChange} value={activeTargetId}>
            <option value="">Custom coordinates</option>
            {#each contacts as contact}
              <option value={contact.id}>{contact.id} · {contact.name}</option>
            {/each}
          </select>
        </label>

        <div class="profile-selector">
          {#each ["aggressive", "balanced", "conservative"] as candidate}
            <button class:selected={profile === candidate} type="button" on:click={() => { profile = candidate as ProfileName; void refreshSolutions(); }}>
              {candidate}
            </button>
          {/each}
        </div>
      </div>
    {/if}

    {#if rawTier}
      <div class="coordinate-grid">
        <label><span>X</span><input bind:value={xInput} on:blur={onCoordinateBlur} placeholder="0" /></label>
        <label><span>Y</span><input bind:value={yInput} on:blur={onCoordinateBlur} placeholder="0" /></label>
        <label><span>Z</span><input bind:value={zInput} on:blur={onCoordinateBlur} placeholder="0" /></label>
      </div>
      <div class="velocity-grid">
        <label><span>Vx target</span><input bind:value={vxInput} placeholder="optional" /></label>
        <label><span>Vy target</span><input bind:value={vyInput} placeholder="optional" /></label>
        <label><span>Vz target</span><input bind:value={vzInput} placeholder="optional" /></label>
      </div>
    {/if}

    {#if arcadeTier}
      {#if activeTargetId}
        <div class="target-indicator locked">
          <span class="target-dot"></span>
          TARGET LOCKED: {contacts.find(c => c.id === activeTargetId)?.name || activeTargetId}
        </div>
      {:else}
        <div class="target-indicator none">
          <span class="target-dot empty"></span>
          NO TARGET — ping sensors and lock a contact
        </div>
      {/if}
      <div class="command-grid arcade">
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("rendezvous")}>RENDEZVOUS</button>
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("intercept")}>INTERCEPT</button>
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("match")}>MATCH VELOCITY</button>
        <button disabled={busy} on:click={() => engageCommand("hold")}>HOLD POSITION</button>
      </div>
    {:else if cpuAssistTier}
      <div class="assist-shell">
        <div class="assist-header">
          <div>
            <div class="eyebrow">Recommended Solution</div>
            <div class="assist-title">{recommended ? recommended.profile.toUpperCase() : "No solution loaded"}</div>
          </div>
          <button disabled={busy || (!recommended && !canSolve)} on:click={approveRecommended}>
            APPROVE
          </button>
        </div>

        {#if recommended}
          <div class="assist-card">
            <div class="assist-stat"><span>ETA</span><strong>{formatDuration(recommended.totalTime)}</strong></div>
            <div class="assist-stat"><span>Fuel</span><strong>{(recommended.fuelCost * 100).toFixed(1)}%</strong></div>
            <div class="assist-stat"><span>Risk</span><strong>{recommended.riskLevel.toUpperCase()}</strong></div>
            <div class="assist-stat"><span>Range</span><strong>{formatDistance(autopilot.distance)}</strong></div>
          </div>
          <div class="assist-notes">{recommended.description}</div>
        {/if}
      </div>
    {:else}
      <div class="command-grid">
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("rendezvous")}>Rendezvous</button>
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("intercept")}>Intercept</button>
        <button disabled={busy || !activeTargetId} on:click={() => engageCommand("match")}>Match Velocity</button>
        <button disabled={busy} on:click={() => engageCommand("hold")}>Hold Position</button>
        <button class="wide" disabled={busy || !hasCoords} on:click={setCourse}>Set Course</button>
        <button class="wide secondary" disabled={navBusy || !canSolve} on:click={refreshSolutions}>Refresh Solutions</button>
      </div>
    {/if}

    {#if rawTier}
      <div class="solutions-shell">
        <div class="eyebrow">Nav Solutions</div>
        {#if navBusy}
          <div class="empty">Calculating profiles…</div>
        {:else if navSolutions.length === 0}
          <div class="empty">Choose a target or coordinates to generate profiles.</div>
        {:else}
          <div class="solution-table">
            {#each navSolutions as solution}
              <button type="button" class:selected={profile === solution.profile} class="solution-card" on:click={() => (profile = solution.profile)}>
                <div class="solution-header">
                  <strong>{solution.profile.toUpperCase()}</strong>
                  <span>{solution.riskLevel.toUpperCase()}</span>
                </div>
                <div class="solution-row"><span>ETA</span><span>{formatDuration(solution.totalTime)}</span></div>
                <div class="solution-row"><span>Fuel</span><span>{(solution.fuelCost * 100).toFixed(1)}%</span></div>
                <div class="solution-row"><span>Accuracy</span><span>{formatDistance(solution.accuracy)}</span></div>
                <div class="solution-row"><span>Flip</span><span>{formatDuration(solution.estimatedFlipTime)}</span></div>
                <div class="solution-row"><span>Max thrust</span><span>{(solution.maxThrust * 100).toFixed(0)}%</span></div>
                <p>{solution.description}</p>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .content {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .selector-row,
  .assist-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  label {
    display: grid;
    gap: 4px;
    min-width: 0;
    flex: 1;
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  select,
  input {
    width: 100%;
  }

  .profile-selector,
  .command-grid {
    display: grid;
    gap: var(--space-xs);
  }

  .profile-selector {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    flex: 1;
  }

  .profile-selector button.selected,
  .solution-card.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.55);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .coordinate-grid,
  .velocity-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .command-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .command-grid.arcade {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .command-grid.arcade button {
    min-height: 74px;
    font-family: var(--font-mono);
    letter-spacing: 0.08em;
  }

  .target-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  .target-indicator.locked {
    background: rgba(0, 255, 136, 0.08);
    border: 1px solid var(--status-nominal);
    color: var(--status-nominal);
  }

  .target-indicator.none {
    background: rgba(255, 170, 0, 0.06);
    border: 1px solid var(--status-warning);
    color: var(--status-warning);
  }

  .target-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--status-nominal);
    flex-shrink: 0;
    animation: pulse-lock 1.5s ease-in-out infinite;
  }

  .target-dot.empty {
    background: transparent;
    border: 2px solid var(--status-warning);
    animation: none;
  }

  @keyframes pulse-lock {
    0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--status-nominal); }
    50% { opacity: 0.6; box-shadow: none; }
  }

  .command-grid .wide {
    grid-column: span 2;
  }

  .command-grid .secondary {
    border-style: dashed;
  }

  .solutions-shell,
  .assist-shell {
    display: grid;
    gap: var(--space-sm);
  }

  .solution-table {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .solution-card,
  .assist-card {
    display: grid;
    gap: 6px;
    padding: 10px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.02);
    text-align: left;
  }

  .solution-header,
  .solution-row,
  .assist-stat {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: baseline;
  }

  .solution-card strong,
  .assist-title,
  .assist-stat strong {
    font-family: var(--font-mono);
  }

  .solution-card p,
  .assist-notes,
  .empty,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .eyebrow {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
  }

  .assist-title {
    font-size: 1rem;
  }

  .assist-card {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 900px) {
    .selector-row,
    .assist-header {
      flex-direction: column;
      align-items: stretch;
    }

    .solution-table,
    .assist-card,
    .coordinate-grid,
    .velocity-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
