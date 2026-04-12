<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getAuthorizedWeapons,
    getLauncherInventory,
    getLockedTargetId,
    getTacticalProposals,
  } from "./tacticalData.js";

  $: ship = extractShipState($gameState);
  $: authorized = getAuthorizedWeapons(ship);
  $: inventory = getLauncherInventory(ship);
  $: proposals = getTacticalProposals(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: activeTargetId = $selectedTacticalTargetId || lockedTargetId;
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  async function fireNow(command: "fire_railgun" | "launch_torpedo" | "launch_missile") {
    const params: Record<string, unknown> = {};
    if (activeTargetId) params.target = activeTargetId;
    if (command !== "fire_railgun") params.profile = "direct";
    await wsClient.sendShipCommand(command, params);
  }

  async function toggleAuthorization(kind: "railgun" | "torpedo" | "missile") {
    const enabled = authorized[kind];
    await wsClient.sendShipCommand(enabled ? "deauthorize_weapon" : "authorize_weapon", {
      weapon_type: kind,
      profile: "direct",
    });
  }

  async function approveProposal(proposalId: string) {
    await wsClient.sendShipCommand("approve_tactical", { proposal_id: proposalId });
  }

  function ammoPercent(loaded: unknown, capacity: unknown): string {
    const l = Number(loaded ?? 0);
    const c = Number(capacity ?? 0);
    if (!c) return "0%";
    return `${Math.round((l / c) * 100)}%`;
  }
</script>

<Panel title="Fire Authorization" domain="weapons" priority={arcadeTier || cpuAssistTier ? "primary" : "secondary"} className="fire-authorization-panel">
  <div class="shell">
    {#if arcadeTier}
      <div class="arcade-grid">
        <button class="arcade-btn railgun" on:click={() => fireNow("fire_railgun")}>
          <span>RAILGUN</span>
        </button>
        <button class="arcade-btn torpedo" on:click={() => fireNow("launch_torpedo")}>
          <span>TORPEDO</span>
          <strong>{ammoPercent(inventory.torpedoes.loaded, inventory.torpedoes.capacity)}</strong>
        </button>
        <button class="arcade-btn missile" on:click={() => fireNow("launch_missile")}>
          <span>MISSILE</span>
          <strong>{ammoPercent(inventory.missiles.loaded, inventory.missiles.capacity)}</strong>
        </button>
      </div>
    {:else if cpuAssistTier}
      <div class="auth-grid">
        {#each ["railgun", "torpedo", "missile"] as weapon}
          <button class:selected={authorized[weapon]} type="button" on:click={() => toggleAuthorization(weapon as "railgun" | "torpedo" | "missile")}>
            <span>{weapon.toUpperCase()}</span>
            <strong>{authorized[weapon] ? "AUTHORIZED" : "HOLD"}</strong>
          </button>
        {/each}
      </div>

      <div class="proposal-list">
        {#if proposals.length === 0}
          <div class="empty">No pending tactical approvals.</div>
        {:else}
          {#each proposals as proposal}
            <div class="proposal-card">
              <strong>{proposal.action ?? "proposal"}</strong>
              <span>{proposal.target ?? "--"} · {proposal.confidence ? `${Math.round(Number(proposal.confidence) * 100)}%` : "pending"}</span>
              <span>{proposal.reason ?? "Awaiting approval"}</span>
              <button on:click={() => approveProposal(String(proposal.proposal_id ?? ""))}>APPROVE</button>
            </div>
          {/each}
        {/if}
      </div>
    {:else}
      <div class="manual-note">RAW and MANUAL tiers use explicit weapon panels below.</div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .proposal-list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .arcade-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .arcade-btn,
  .auth-grid button,
  .proposal-card {
    display: grid;
    gap: 6px;
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
  }

  .arcade-btn span,
  .manual-note,
  .proposal-card span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .arcade-btn strong,
  .auth-grid strong,
  .proposal-card strong {
    font-family: var(--font-mono);
  }

  .auth-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .auth-grid button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .proposal-card,
  .manual-note {
    background: rgba(255, 255, 255, 0.02);
  }
</style>
