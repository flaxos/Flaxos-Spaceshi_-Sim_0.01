<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    POWER_CATEGORY_ORDER,
    OPS_SYSTEM_PRIORITY_ORDER,
    type PowerCategory,
    ENGINEERING_SYSTEM_LABELS,
    formatPercent,
    formatDuration,
    getFieldRepair,
    getAutoOpsState,
    getOpsProposals,
    getOpsShip,
    getOpsState,
    getRepairTargets,
    getRepairTeams,
    getSystemPriority,
    powerCategoryWeights,
    toNumber,
    toStringValue,
    translatePowerCategoryWeights,
  } from "./opsData.js";

  let feedback = "";
  let dirty = false;
  let weights: Record<PowerCategory, number> = {
    propulsion: 0.25,
    weapons: 0.15,
    sensors: 0.15,
    comms: 0.05,
    life_support: 0.05,
  };

  $: ship = getOpsShip($gameState);
  $: ops = getOpsState(ship);
  $: autoOps = getAutoOpsState(ship);
  $: repairTeams = getRepairTeams(ship);
  $: repairTargets = getRepairTargets(ship);
  $: fieldRepair = getFieldRepair(ship);
  $: proposals = getOpsProposals(ship);
  $: cpuAssistTier = $tier === "cpu-assist";
  $: manualTier = $tier === "manual";
  $: autoOpsEnabled = Boolean(autoOps.enabled);
  $: if (!dirty) weights = { ...powerCategoryWeights(ship) };

  async function transmitPowerAllocation() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("set_power_allocation", {
        allocation: translatePowerCategoryWeights(weights),
      });
      dirty = false;
      feedback = "Power allocation updated";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Allocation update failed";
    }
  }

  function adjustWeight(category: PowerCategory, value: number) {
    dirty = true;
    weights = { ...weights, [category]: Math.max(0, Math.min(1, value / 100)) };
  }

  async function dispatchRepair(subsystem: string, teamId = "") {
    feedback = "";
    try {
      const params: Record<string, unknown> = { subsystem };
      if (teamId) params.team = teamId;
      await wsClient.sendShipCommand("dispatch_repair", params);
      feedback = `Repair team dispatched to ${subsystem}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Dispatch failed";
    }
  }

  async function cancelRepair(subsystem: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("cancel_repair", { subsystem });
      feedback = `Repair cancelled for ${subsystem}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Cancel failed";
    }
  }

  async function setSystemPriority(subsystem: string, priority: number) {
    try {
      await wsClient.sendShipCommand("set_system_priority", { subsystem, priority });
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Priority update failed";
    }
  }

  async function toggleAutoOps(enabled: boolean) {
    try {
      await wsClient.sendShipCommand(enabled ? "enable_auto_ops" : "disable_auto_ops", {});
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Auto-ops command failed";
    }
  }

  async function approveProposal(proposalId: string) {
    await wsClient.sendShipCommand("approve_ops", { proposal_id: proposalId });
  }

  async function denyProposal(proposalId: string) {
    await wsClient.sendShipCommand("deny_ops", { proposal_id: proposalId });
  }
</script>

<Panel title="Ops Control" domain="power" priority={cpuAssistTier ? "primary" : "secondary"} className="ops-control-panel">
  <div class="shell">
    <section class="auto-card">
      <div class="row-head">
        <span>Auto-Ops</span>
        <strong>{autoOpsEnabled ? "ENABLED" : "DISABLED"}</strong>
      </div>
      <div class="toggle-row">
        <button class:active={autoOpsEnabled} type="button" on:click={() => toggleAutoOps(true)}>ENABLE</button>
        <button class:active={!autoOpsEnabled} type="button" on:click={() => toggleAutoOps(false)}>DISABLE</button>
      </div>
    </section>

    {#if cpuAssistTier}
      <section class="proposal-list">
        {#if proposals.length === 0}
          <div class="empty-card">No pending ops approvals.</div>
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
      <section class="power-card">
        <div class="section-title">Power Allocation</div>
        {#each POWER_CATEGORY_ORDER as category}
          <div class="alloc-row">
            <span>{category.replaceAll("_", " ").toUpperCase()}</span>
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={Math.round((weights[category] ?? 0) * 100)}
              on:input={(event) => adjustWeight(category, Number((event.currentTarget as HTMLInputElement).value))}
              on:change={transmitPowerAllocation}
            />
            <strong>{formatPercent((weights[category] ?? 0) * 100)}</strong>
          </div>
        {/each}
      </section>

      <section class="teams-card">
        <div class="section-title">Repair Teams</div>
        {#each repairTeams as team}
          <div class="team-row">
            <strong>{toStringValue(team.team_id, "--")}</strong>
            <span>{toStringValue(team.status, "idle").toUpperCase()}</span>
            <span>{toStringValue(team.assigned_subsystem, "UNASSIGNED")}</span>
            <span>{formatDuration(toNumber(team.transit_remaining, 0))}</span>
          </div>
        {/each}
      </section>

      <section class="dispatch-card">
        <div class="section-title">Damage Dispatch</div>
        {#if repairTargets.length === 0}
          <div class="empty-card">No damaged systems awaiting repair.</div>
        {:else}
          {#each repairTargets as target}
            <div class="target-card">
              <div class="target-head">
                <strong>{target.label.toUpperCase()}</strong>
                <span>{formatPercent(target.damagePercent)}</span>
              </div>
              <div class="target-meta">
                <span>{target.status.toUpperCase()}</span>
                <span>{target.assignedTeam || "NO TEAM"}</span>
              </div>
              <div class="target-actions">
                <button type="button" on:click={() => dispatchRepair(target.id)}>DISPATCH</button>
                <button class="secondary" type="button" on:click={() => cancelRepair(target.id)}>CANCEL</button>
              </div>
            </div>
          {/each}
        {/if}
      </section>

      {#if manualTier}
        <section class="priority-card">
          <div class="section-title">System Priorities</div>
          {#each OPS_SYSTEM_PRIORITY_ORDER as subsystem}
            <div class="priority-row">
              <span>{(ENGINEERING_SYSTEM_LABELS[subsystem] ?? subsystem).toUpperCase()}</span>
              <input
                type="range"
                min="0"
                max="10"
                step="1"
                value={getSystemPriority(ship, subsystem)}
                on:change={(event) => setSystemPriority(subsystem, Number((event.currentTarget as HTMLInputElement).value))}
              />
              <strong>{getSystemPriority(ship, subsystem)}</strong>
            </div>
          {/each}
        </section>
      {/if}
    {/if}

    <section class="field-repair-card">
      <div class="row-head">
        <span>Spare Parts</span>
        <strong>{formatPercent(toNumber(fieldRepair.spare_parts_percent, 0))}</strong>
      </div>
      <div class="track">
        <div class="fill" style={`width:${toNumber(fieldRepair.spare_parts_percent, 0).toFixed(0)}%;`}></div>
      </div>
    </section>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .auto-card,
  .power-card,
  .teams-card,
  .dispatch-card,
  .priority-card,
  .proposal-card,
  .field-repair-card,
  .empty-card {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .proposal-list {
    display: grid;
    gap: var(--space-sm);
  }

  .row-head,
  .toggle-row,
  .proposal-head,
  .team-row,
  .target-head,
  .target-meta,
  .priority-row,
  .alloc-row,
  .target-actions,
  .proposal-actions {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .alloc-row input,
  .priority-row input {
    flex: 1;
  }

  .section-title,
  .row-head span,
  .alloc-row span,
  .team-row span,
  .target-meta,
  .proposal-target,
  .proposal-reason,
  .feedback,
  .empty-card {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
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

  button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  button.secondary {
    color: var(--text-secondary);
  }

  .track {
    height: 10px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.35), var(--tier-accent));
  }

  .feedback {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    color: var(--status-info);
    border: 1px solid rgba(68, 136, 255, 0.28);
    background: rgba(68, 136, 255, 0.08);
  }
</style>
