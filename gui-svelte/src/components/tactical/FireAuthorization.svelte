<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import ProposalQueue from "../shared/ProposalQueue.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getAuthorizedWeapons,
    getAutoTacticalState,
    getLauncherInventory,
    getLockedTargetId,
  } from "./tacticalData.js";
  import {
    fireArcadeWeapon,
    setEngagementRules,
    toggleAutoTactical as setAutoTacticalEnabled,
    toggleWeaponAuthorization,
  } from "./tacticalActions.js";
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

  let firingNow: string | null = null;
  let engagementPending = false;
  let autoTacticalPending = false;

  async function fireNow(weaponType: "railgun" | "torpedo" | "missile") {
    if (firingNow) return;
    firingNow = weaponType;
    try {
      await fireArcadeWeapon(weaponType, activeTargetId || undefined);
    } finally {
      firingNow = null;
    }
  }

  async function toggleAuthorization(kind: "railgun" | "torpedo" | "missile") {
    await toggleWeaponAuthorization(kind, authorized[kind], { profile: "direct" });
  }

  async function toggleAutoTactical() {
    if (autoTacticalPending) return;
    autoTacticalPending = true;
    try {
      await setAutoTacticalEnabled(autoTacticalEnabled);
    } finally {
      autoTacticalPending = false;
    }
  }

  async function setEngagement(key: string) {
    if (engagementPending) return;
    engagementPending = true;
    try {
      await setEngagementRules(key);
    } finally {
      engagementPending = false;
    }
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
        <button
          class="arcade-btn railgun"
          disabled={firingNow === "railgun"}
          title={!activeTargetId ? "Select a target first" : "Fire railgun at locked target"}
          on:click={() => fireNow("railgun")}
        >
          <span>RAILGUN</span>
        </button>
        <button
          class="arcade-btn torpedo"
          disabled={firingNow === "torpedo" || Number(inventory.torpedoes.loaded) <= 0}
          title={Number(inventory.torpedoes.loaded) <= 0 ? "No torpedoes loaded" : !activeTargetId ? "Select a target first" : "Fire torpedo at locked target"}
          on:click={() => fireNow("torpedo")}
        >
          <span>TORPEDO</span>
          <strong>{ammoPercent(inventory.torpedoes.loaded, inventory.torpedoes.capacity)}</strong>
        </button>
        <button
          class="arcade-btn missile"
          disabled={firingNow === "missile" || Number(inventory.missiles.loaded) <= 0}
          title={Number(inventory.missiles.loaded) <= 0 ? "No missiles loaded" : !activeTargetId ? "Select a target first" : "Fire missile at locked target"}
          on:click={() => fireNow("missile")}
        >
          <span>MISSILE</span>
          <strong>{ammoPercent(inventory.missiles.loaded, inventory.missiles.capacity)}</strong>
        </button>
        <button
          class="arcade-btn pdc"
          disabled={firingNow === "pdc"}
          title={!activeTargetId ? "Select a target first" : "Fire PDC at locked target"}
          on:click={() => fireNow("pdc")}
        >
          <span>PDC</span>
        </button>
      </div>
    {:else if cpuAssistTier}
      <!-- Auto-tactical enable/disable -->
      <button
        class="auto-toggle"
        class:active={autoTacticalEnabled}
        disabled={autoTacticalPending}
        title={autoTacticalEnabled ? "Disable autonomous weapon engagement" : "Enable autonomous weapon engagement"}
        type="button"
        on:click={toggleAutoTactical}
      >
        AUTO-TACTICAL: {autoTacticalPending ? "…" : autoTacticalEnabled ? "ENABLED" : "DISABLED"}
      </button>

      <!-- Engagement rules -->
      <div class="engagement-row">
        {#each ENGAGEMENT_MODES as { key, label }}
          <button
            class:selected={engagementMode === key}
            disabled={engagementPending}
            title={{ weapons_free: "Engage any valid target", weapons_hold: "Do not fire — hold all weapons", defensive_only: "Engage only inbound munitions" }[key]}
            type="button"
            on:click={() => setEngagement(key)}
          >
            {label}
          </button>
        {/each}
      </div>

      <!-- Weapon auth toggles -->
      <div class="auth-grid">
        {#each ["railgun", "torpedo", "missile", "pdc"] as weapon}
          <button
            class:selected={authorized[weapon]}
            type="button"
            on:click={() => toggleAuthorization(weapon as "railgun" | "torpedo" | "missile" | "pdc")}
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
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
