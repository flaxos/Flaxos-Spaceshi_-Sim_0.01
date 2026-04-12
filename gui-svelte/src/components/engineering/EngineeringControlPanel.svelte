<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    formatDriveLimit,
    formatFuelBurnRate,
    formatFuelTime,
    formatSpeed,
    getEngineeringProposals,
    getEngineeringShip,
    getEngineeringState,
    getReactorSummary,
    getThermalState,
    toNumber,
    toStringValue,
  } from "./engineeringData.js";

  const RADIATOR_PANELS = ["P1", "P2", "P3", "S1", "S2", "S3"];

  let reactorDraft = 0;
  let driveDraft = 100;
  let reactorTimer: number | null = null;
  let driveTimer: number | null = null;
  let editMode = "";
  let feedback = "";
  let showVentConfirm = false;
  let pending = false;

  $: ship = getEngineeringShip($gameState);
  $: engineering = getEngineeringState(ship);
  $: thermal = getThermalState(ship);
  $: summary = getReactorSummary(ship);
  $: proposals = getEngineeringProposals(ship);
  $: cpuAssistTier = $tier === "cpu-assist";
  $: arcadeTier = $tier === "arcade";
  $: radiatorsDeployed = Boolean(engineering.radiators_deployed);
  $: radiatorPriority = toStringValue(engineering.radiator_priority, "balanced");
  $: ventAvailable = Boolean(engineering.emergency_vent_available ?? true);
  $: ventActive = Boolean(engineering.emergency_vent_active);
  $: if (editMode !== "reactor") reactorDraft = Math.round(summary.output * 100);
  $: if (editMode !== "drive") driveDraft = Math.round(summary.driveLimit * 100);

  function scheduleCommand(kind: "reactor" | "drive", value: number) {
    editMode = kind;
    if (kind === "reactor") {
      reactorDraft = value;
      if (reactorTimer != null) window.clearTimeout(reactorTimer);
      reactorTimer = window.setTimeout(async () => {
        await sendCommand("set_reactor_output", { output: value });
        editMode = "";
      }, 60);
      return;
    }

    driveDraft = value;
    if (driveTimer != null) window.clearTimeout(driveTimer);
    driveTimer = window.setTimeout(async () => {
      await sendCommand("throttle_drive", { limit: value });
      editMode = "";
    }, 60);
  }

  async function sendCommand(command: string, params: Record<string, unknown>) {
    pending = true;
    feedback = "";
    try {
      await wsClient.sendShipCommand(command, params);
    } catch (error) {
      feedback = error instanceof Error ? error.message : `${command} failed`;
    } finally {
      pending = false;
    }
  }

  async function setRadiators(deployed: boolean) {
    await sendCommand("manage_radiators", { deployed });
  }

  async function setRadiatorPriority(priority: string) {
    await sendCommand("manage_radiators", { priority });
  }

  async function approveProposal(proposalId: string) {
    await sendCommand("approve_engineering", { proposal_id: proposalId });
  }

  async function denyProposal(proposalId: string) {
    await sendCommand("deny_engineering", { proposal_id: proposalId });
  }

  async function triggerEmergencyVent() {
    showVentConfirm = false;
    await sendCommand("emergency_vent", { confirm: true });
  }
</script>

<Panel title="Engineering Control" domain="power" priority={cpuAssistTier ? "primary" : "secondary"} className="engineering-control-panel">
  <div class="shell">
    {#if cpuAssistTier}
      <section class="proposal-list">
        <div class="assist-note">
          <strong>{toStringValue(engineering.status, "AUTO-ENGINEERING").toUpperCase()}</strong>
          <span>{proposals.length} pending proposal{proposals.length === 1 ? "" : "s"}</span>
        </div>

        {#if proposals.length === 0}
          <div class="empty-card">
            <strong>Stable</strong>
            <span>Auto-ops is holding reactor, radiators, and drive governor inside limits.</span>
          </div>
        {:else}
          {#each proposals as proposal}
            <div class="proposal-card">
              <div class="proposal-head">
                <strong>{proposal.action.replaceAll("_", " ").toUpperCase()}</strong>
                <span>{Math.round(proposal.confidence * 100)}%</span>
              </div>
              <div class="proposal-target">{proposal.target.toUpperCase()}</div>
              <div class="proposal-reason">{proposal.reason}</div>
              <div class="proposal-actions">
                <button type="button" on:click={() => approveProposal(proposal.proposalId)}>APPROVE</button>
                <button class="secondary" type="button" on:click={() => denyProposal(proposal.proposalId)}>DENY</button>
              </div>
            </div>
          {/each}
        {/if}
      </section>
    {:else}
      <section class="control-card">
        <div class="row-head">
          <span>Reactor Output</span>
          <strong>{reactorDraft}%</strong>
        </div>
        <input type="range" min="0" max="100" step="1" value={reactorDraft} on:input={(event) => scheduleCommand("reactor", Number((event.currentTarget as HTMLInputElement).value))} />
      </section>

      <section class="control-card">
        <div class="row-head">
          <span>Drive Limit</span>
          <strong>{driveDraft}%</strong>
        </div>
        <input type="range" min="0" max="100" step="1" value={driveDraft} on:input={(event) => scheduleCommand("drive", Number((event.currentTarget as HTMLInputElement).value))} />
      </section>

      <section class="fuel-card">
        <div class="row-head">
          <span>Fuel Monitor</span>
          <strong>{summary.fuelPercent.toFixed(0)}%</strong>
        </div>
        <div class="track">
          <div class="fill fuel" style={`width:${summary.fuelPercent.toFixed(0)}%;`}></div>
        </div>
        <div class="detail-grid">
          <div><span>Burn</span><strong>{formatFuelBurnRate(summary.burnRate)}</strong></div>
          <div><span>Delta-V</span><strong>{formatSpeed(summary.deltaV)}</strong></div>
          <div><span>Limit</span><strong>{formatDriveLimit(summary.driveLimit)}</strong></div>
          <div><span>Remaining</span><strong>{formatFuelTime(summary.timeRemaining)}</strong></div>
        </div>
      </section>

      <section class="radiator-card">
        <div class="row-head">
          <span>Radiator Panels</span>
          <strong>{radiatorsDeployed ? "DEPLOYED" : "RETRACTED"}</strong>
        </div>
        <div class="panel-grid">
          {#each RADIATOR_PANELS as panelId}
            <button
              type="button"
              class:active={radiatorsDeployed}
              on:click={() => setRadiators(!radiatorsDeployed)}
            >
              {panelId}
            </button>
          {/each}
        </div>
        <div class="priority-row">
          {#each ["balanced", "cooling", "stealth"] as priority}
            <button class:selected={radiatorPriority === priority} type="button" on:click={() => setRadiatorPriority(priority)}>
              {priority.replaceAll("_", " ").toUpperCase()}
            </button>
          {/each}
        </div>
      </section>

      <section class="vent-card">
        <div class="row-head">
          <span>Emergency Vent</span>
          <strong class:warning={toNumber(thermal.temperature_percent) >= 70} class:critical={toNumber(thermal.temperature_percent) >= 90}>
            {ventActive ? "ACTIVE" : ventAvailable ? "ARMED" : "SPENT"}
          </strong>
        </div>
        <button
          type="button"
          class="vent-button"
          disabled={!ventAvailable || ventActive || pending}
          on:click={() => showVentConfirm = true}
        >
          {ventActive ? "VENTING..." : arcadeTier ? "VENT NOW" : "EMERGENCY VENT"}
        </button>
      </section>
    {/if}

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>

  {#if showVentConfirm}
    <div class="modal-backdrop">
      <div class="modal">
        <strong>Confirm Coolant Vent</strong>
        <p>This is irreversible and will permanently dump coolant reserves.</p>
        <div class="modal-actions">
          <button type="button" on:click={triggerEmergencyVent}>CONFIRM VENT</button>
          <button class="secondary" type="button" on:click={() => showVentConfirm = false}>CANCEL</button>
        </div>
      </div>
    </div>
  {/if}
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .control-card,
  .fuel-card,
  .radiator-card,
  .vent-card,
  .proposal-card,
  .assist-note,
  .empty-card {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent);
  }

  .proposal-list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .row-head,
  .proposal-head,
  .detail-grid {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .detail-grid span,
  .row-head span,
  .proposal-target,
  .proposal-reason,
  .assist-note span,
  .empty-card span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .warning {
    color: var(--status-warning);
  }

  .critical {
    color: var(--status-critical);
  }

  input[type="range"] {
    width: 100%;
  }

  .track {
    height: 10px;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    overflow: hidden;
  }

  .fill {
    height: 100%;
  }

  .fill.fuel {
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.35), var(--tier-accent));
  }

  .panel-grid,
  .priority-row,
  .proposal-actions {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  .panel-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  button.active,
  button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  button.secondary {
    color: var(--text-secondary);
  }

  .vent-button {
    background: rgba(255, 68, 68, 0.12);
    border-color: rgba(255, 68, 68, 0.45);
    color: var(--status-critical);
  }

  .proposal-target {
    color: var(--tier-accent);
  }

  .feedback {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    color: var(--status-warning);
    border: 1px solid rgba(255, 170, 0, 0.25);
    background: rgba(255, 170, 0, 0.08);
  }

  .modal-backdrop {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgba(4, 5, 10, 0.76);
  }

  .modal {
    display: grid;
    gap: var(--space-sm);
    width: min(340px, calc(100% - 24px));
    padding: 14px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(255, 68, 68, 0.35);
    background: var(--bg-panel);
  }

  .modal p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.82rem;
  }

  .modal-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-sm);
  }

  @media (max-width: 760px) {
    .panel-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
</style>
