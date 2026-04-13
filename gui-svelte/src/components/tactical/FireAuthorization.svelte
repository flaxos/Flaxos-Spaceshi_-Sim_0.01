<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import ProposalQueue from "../shared/ProposalQueue.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getAuthorizedWeapons,
    getAutoTacticalState,
    getLauncherInventory,
    getLockedTargetId,
  } from "./tacticalData.js";
  import { proposals } from "../../lib/stores/proposals.js";

  $: ship = extractShipState($gameState);
  $: authorized = getAuthorizedWeapons(ship);
  $: inventory = getLauncherInventory(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: activeTargetId = $selectedTacticalTargetId || lockedTargetId;
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  // CPU-ASSIST: auto-tactical state
  $: autoTactical = getAutoTacticalState(ship);
  $: autoTacticalEnabled = Boolean(autoTactical.enabled);
  $: engagementMode = String(autoTactical.engagement_mode ?? "weapons_hold");

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

  async function toggleAutoTactical() {
    await wsClient.sendShipCommand(
      autoTacticalEnabled ? "disable_auto_tactical" : "enable_auto_tactical",
      {}
    );
  }

  async function setEngagementRules(mode: string) {
    await wsClient.sendShipCommand("set_engagement_rules", { mode });
  }

  function ammoPercent(loaded: unknown, capacity: unknown): string {
    const l = Number(loaded ?? 0);
    const c = Number(capacity ?? 0);
    if (!c) return "0%";
    return `${Math.round((l / c) * 100)}%`;
  }

  const ENGAGEMENT_MODES = [
    { key: "weapons_free", label: "WPN FREE" },
    { key: "weapons_hold", label: "WPN HOLD" },
    { key: "defensive_only", label: "DEFENSIVE" },
  ];
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
      <!-- Auto-tactical enable/disable -->
      <button
        class="auto-toggle"
        class:active={autoTacticalEnabled}
        type="button"
        on:click={toggleAutoTactical}
      >
        AUTO-TACTICAL: {autoTacticalEnabled ? "ENABLED" : "DISABLED"}
      </button>

      <!-- Engagement rules -->
      <div class="engagement-row">
        {#each ENGAGEMENT_MODES as { key, label }}
          <button
            class:selected={engagementMode === key}
            type="button"
            on:click={() => setEngagementRules(key)}
          >
            {label}
          </button>
        {/each}
      </div>

      <!-- Weapon auth toggles -->
      <div class="auth-grid">
        {#each ["railgun", "torpedo", "missile"] as weapon}
          <button
            class:selected={authorized[weapon]}
            type="button"
            on:click={() => toggleAuthorization(weapon as "railgun" | "torpedo" | "missile")}
          >
            <span>{weapon.toUpperCase()}</span>
            <strong>{authorized[weapon] ? "AUTHORIZED" : "HOLD"}</strong>
          </button>
        {/each}
      </div>

      <!-- Proposal queue -->
      <ProposalQueue proposals={$proposals.tactical} station="tactical" />
    {:else}
      <div class="manual-note">RAW and MANUAL tiers use explicit weapon panels below.</div>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .arcade-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .arcade-btn {
    display: grid;
    gap: 6px;
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
  }

  .arcade-btn span,
  .manual-note {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .arcade-btn strong {
    font-family: var(--font-mono);
  }

  /* Auto-tactical toggle */
  .auto-toggle {
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }

  .auto-toggle.active {
    border-color: rgba(var(--tier-accent-rgb), 0.6);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  /* Engagement rules */
  .engagement-row {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .engagement-row button {
    padding: 6px 4px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
    font-family: var(--font-mono);
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    cursor: pointer;
    color: var(--text-secondary);
    transition: background 0.1s, border-color 0.1s, color 0.1s;
  }

  .engagement-row button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
    color: var(--text-primary);
  }

  /* Weapon authorization grid */
  .auth-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .auth-grid button {
    display: grid;
    gap: 4px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.02);
    cursor: pointer;
    transition: background 0.1s, border-color 0.1s;
  }

  .auth-grid button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .auth-grid span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .auth-grid strong {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-primary);
  }

  .manual-note {
    padding: 10px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
  }
</style>
