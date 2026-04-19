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
    getWeaponMounts,
    toNumber,
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
  $: mounts = getWeaponMounts(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: activeTargetId = $selectedTacticalTargetId || lockedTargetId;
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  // CPU-ASSIST: auto-tactical state
  $: autoTactical = getAutoTacticalState(ship);
  $: autoTacticalEnabled = Boolean(autoTactical.enabled);
  $: engagementMode = String(autoTactical.engagement_mode ?? "weapons_hold");

  // Track mount shots_fired per weaponType to detect "just fired" events
  // Map: weaponType → last known total ammo (decrements = shot fired)
  let prevAmmo: Record<string, number> = {};
  let justFired: Set<string> = new Set();
  let justFiredTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  $: detectFired(mounts);

  function detectFired(currentMounts: typeof mounts) {
    for (const mount of currentMounts) {
      const key = mount.weaponType;
      const cur = mount.ammo;
      const prev = prevAmmo[key];
      if (prev !== undefined && cur < prev) {
        triggerFired(key);
      }
      prevAmmo[key] = cur;
    }
  }

  function triggerFired(key: string) {
    clearTimeout(justFiredTimers[key]);
    justFired = new Set(justFired).add(key);
    justFiredTimers[key] = setTimeout(() => {
      const next = new Set(justFired);
      next.delete(key);
      justFired = next;
    }, 600);
  }

  let firingNow: string | null = null;
  let engagementPending = false;
  let autoTacticalPending = false;

  async function fireNow(weaponType: "railgun" | "torpedo" | "missile" | "pdc") {
    if (firingNow) return;
    firingNow = weaponType;
    try {
      await fireArcadeWeapon(weaponType, activeTargetId || undefined);
    } finally {
      firingNow = null;
    }
  }

  async function toggleAuthorization(kind: "railgun" | "torpedo" | "missile" | "pdc") {
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

  function ammoPercent(loaded: unknown, capacity: unknown): number {
    const l = Number(loaded ?? 0);
    const c = Number(capacity ?? 0);
    if (!c) return 0;
    return Math.round((l / c) * 100);
  }

  // Per-weapon styling
  const WEAPON_META: Record<string, { color: string; rgb: string; label: string }> = {
    railgun: { color: "#e83030", rgb: "232,48,48",   label: "RAILGUN" },
    torpedo: { color: "#efa020", rgb: "239,160,32",  label: "TORPEDO" },
    missile: { color: "#1e8cff", rgb: "30,140,255",  label: "MISSILE" },
    pdc:     { color: "#00dd6a", rgb: "0,221,106",   label: "PDC" },
  };

  const ENGAGEMENT_MODES = [
    { key: "weapons_free", label: "WPN FREE", color: "#e83030" },
    { key: "weapons_hold", label: "WPN HOLD", color: "#3a3a52" },
    { key: "defensive_only", label: "DEFENSIVE", color: "#1e8cff" },
  ];

  const ENGAGEMENT_TIPS: Record<string, string> = {
    weapons_free: "Engage any valid target on sight",
    weapons_hold: "Do not fire — hold all weapons",
    defensive_only: "Engage only inbound munitions",
  };

  // Ammo for display on auth buttons
  function weaponAmmo(type: string): { loaded: number; capacity: number } {
    if (type === "torpedo") {
      return {
        loaded: toNumber(inventory.torpedoes.loaded),
        capacity: toNumber(inventory.torpedoes.capacity, toNumber(inventory.torpedoes.max, 0)),
      };
    }
    if (type === "missile") {
      return {
        loaded: toNumber(inventory.missiles.loaded),
        capacity: toNumber(inventory.missiles.capacity, toNumber(inventory.missiles.max, 0)),
      };
    }
    const mount = mounts.find((m) => m.weaponType === type);
    if (mount) return { loaded: mount.ammo, capacity: mount.ammoCapacity };
    return { loaded: 0, capacity: 0 };
  }
</script>

<Panel title="Fire Authorization" domain="weapons" priority={arcadeTier || cpuAssistTier ? "primary" : "secondary"} className="fire-authorization-panel">
  <div class="shell">
    {#if arcadeTier}
      <!-- ── Arcade: simple fire buttons per weapon type ── -->
      <div class="arcade-grid">
        {#each ["railgun", "torpedo", "missile", "pdc"] as wtype}
          {@const meta = WEAPON_META[wtype]}
          {@const ammo = weaponAmmo(wtype)}
          {@const pct = ammoPercent(ammo.loaded, ammo.capacity)}
          {@const isFiring = firingNow === wtype}
          {@const hasAmmo = wtype === "railgun" || wtype === "pdc" || ammo.loaded > 0}
          <button
            class="arcade-btn"
            class:firing={isFiring}
            class:just-fired={justFired.has(wtype)}
            disabled={isFiring || !hasAmmo}
            style="--wc:{meta.color};--wr:{meta.rgb};"
            title={!hasAmmo ? `No ${wtype}s loaded` : !activeTargetId ? "Select a target first" : `Fire ${wtype} at locked target`}
            on:click={() => fireNow(wtype as "railgun" | "torpedo" | "missile" | "pdc")}
          >
            <span class="btn-label">{isFiring ? "FIRING…" : meta.label}</span>
            {#if ammo.capacity > 0}
              <div class="ammo-bar-track">
                <div class="ammo-bar-fill" style="width:{pct}%;background:var(--wc)"></div>
              </div>
              <span class="ammo-count">{ammo.loaded}/{ammo.capacity}</span>
            {/if}
          </button>
        {/each}
      </div>

    {:else if cpuAssistTier}
      <!-- ── CPU-Assist: auto-tactical + engagement rules + auth toggles ── -->

      <button
        class="auto-toggle"
        class:active={autoTacticalEnabled}
        disabled={autoTacticalPending}
        title={autoTacticalEnabled ? "Disable autonomous weapon engagement" : "Enable autonomous weapon engagement"}
        type="button"
        on:click={toggleAutoTactical}
      >
        <span class="dot" class:nom={autoTacticalEnabled} class:dim={!autoTacticalEnabled}></span>
        AUTO-TACTICAL
        <strong>{autoTacticalPending ? "…" : autoTacticalEnabled ? "ENABLED" : "DISABLED"}</strong>
      </button>

      <!-- Engagement rules -->
      <div class="section-label">Engagement Rules</div>
      <div class="engagement-row">
        {#each ENGAGEMENT_MODES as { key, label, color }}
          <button
            class:selected={engagementMode === key}
            style="--ec:{color};"
            disabled={engagementPending}
            title={ENGAGEMENT_TIPS[key]}
            type="button"
            on:click={() => setEngagement(key)}
          >{label}</button>
        {/each}
      </div>

      <!-- Weapon auth toggles -->
      <div class="section-label">Weapon Authorization</div>
      <div class="auth-grid">
        {#each ["railgun", "torpedo", "missile", "pdc"] as wtype}
          {@const meta = WEAPON_META[wtype]}
          {@const isAuth = Boolean(authorized[wtype])}
          {@const ammo = weaponAmmo(wtype)}
          {@const pct = ammoPercent(ammo.loaded, ammo.capacity)}
          {@const fired = justFired.has(wtype)}
          <button
            class="auth-btn"
            class:authorized={isAuth}
            class:just-fired={fired}
            style="--wc:{meta.color};--wr:{meta.rgb};"
            title={isAuth ? `Deauthorize ${wtype} — computer will cease fire` : `Authorize ${wtype} — computer will engage when solution ready`}
            type="button"
            on:click={() => toggleAuthorization(wtype as "railgun" | "torpedo" | "missile" | "pdc")}
          >
            <div class="auth-head">
              <span class="dot" class:auth-on={isAuth} class:firing={fired}></span>
              <span class="auth-name">{meta.label}</span>
              <strong class="auth-state">{isAuth ? "AUTH" : "HOLD"}</strong>
            </div>
            {#if ammo.capacity > 0}
              <div class="ammo-bar-track">
                <div class="ammo-bar-fill" style="width:{pct}%;background:var(--wc);opacity:{isAuth ? 1 : 0.4};"></div>
              </div>
              <span class="ammo-count">{ammo.loaded}/{ammo.capacity}</span>
            {/if}
          </button>
        {/each}
      </div>

      <!-- Proposal queue -->
      <ProposalQueue proposals={$proposals.tactical} station="tactical" />

    {:else}
      <div class="manual-note">Manual / Raw tiers use the Weapons Workflow panel.</div>
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .section-label {
    font-size: 0.55rem;
    font-family: var(--font-mono);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--tx-dim);
    padding-bottom: 2px;
    border-bottom: 1px solid var(--bd-subtle);
  }

  /* ── Arcade fire buttons ── */
  .arcade-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  .arcade-btn {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 5px;
    padding: 10px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(var(--wr), 0.25);
    background: rgba(var(--wr), 0.06);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  }

  .arcade-btn:hover:not(:disabled) {
    background: rgba(var(--wr), 0.14);
    border-color: rgba(var(--wr), 0.5);
    box-shadow: 0 0 14px rgba(var(--wr), 0.22);
  }

  .arcade-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .arcade-btn.firing {
    animation: weaponPulse 0.35s ease-in-out infinite alternate;
    border-color: var(--wc);
  }

  .arcade-btn.just-fired {
    animation: muzzleFlash 0.55s ease-out forwards;
  }

  .btn-label {
    font-size: 0.65rem;
    font-family: var(--font-mono);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--wc);
    text-align: center;
  }

  /* ── Auth toggles (CPU-Assist) ── */
  .auth-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  .auth-btn {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 5px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--bd-default);
    background: rgba(255, 255, 255, 0.02);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  }

  .auth-btn.authorized {
    border-color: rgba(var(--wr), 0.55);
    background: rgba(var(--wr), 0.1);
    box-shadow: 0 0 12px rgba(var(--wr), 0.18);
    animation: authorizedPulse 2.4s ease-in-out infinite;
  }

  .auth-btn.just-fired {
    animation: muzzleFlash 0.55s ease-out forwards;
  }

  .auth-head {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .auth-name {
    font-size: 0.62rem;
    font-family: var(--font-mono);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--tx-primary);
    flex: 1;
  }

  .auth-state {
    font-size: 0.56rem;
    font-family: var(--font-mono);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--tx-dim);
  }

  .auth-btn.authorized .auth-state {
    color: var(--wc);
  }

  .ammo-count {
    font-size: 0.56rem;
    font-family: var(--font-mono);
    color: var(--tx-sec);
    text-align: right;
  }

  /* ── Status dot ── */
  .dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--tx-dim);
    flex-shrink: 0;
  }

  .dot.nom,
  .dot.auth-on {
    background: var(--wc, var(--nom));
    box-shadow: 0 0 6px var(--wc, var(--nom));
  }

  .dot.dim {
    background: var(--tx-dim);
  }

  .dot.firing {
    background: #fff;
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.8);
    animation: critFlicker 0.15s ease-in-out infinite;
  }

  /* ── Ammo bars ── */
  .ammo-bar-track {
    height: 3px;
    border-radius: 1px;
    background: var(--bg-input);
    overflow: hidden;
  }

  .ammo-bar-fill {
    height: 100%;
    border-radius: 1px;
    transition: width 0.4s ease;
  }

  /* ── Auto-tactical toggle ── */
  .auto-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--bd-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--tx-sec);
    font-family: var(--font-mono);
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }

  .auto-toggle strong {
    margin-left: auto;
    font-size: 0.62rem;
    font-family: var(--font-mono);
  }

  .auto-toggle.active {
    border-color: rgba(0, 221, 106, 0.5);
    background: rgba(0, 221, 106, 0.08);
    color: var(--nom);
  }

  /* ── Engagement rules ── */
  .engagement-row {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  .engagement-row button {
    padding: 7px 4px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--bd-subtle);
    background: rgba(255, 255, 255, 0.02);
    font-family: var(--font-mono);
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    color: var(--tx-sec);
    transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
  }

  .engagement-row button.selected {
    border-color: rgba(var(--ec, 255, 255, 255), 0.6);
    background: rgba(var(--ec, 255, 255, 255), 0.12);
    color: var(--ec, var(--tx-bright));
    box-shadow: 0 0 10px rgba(var(--ec, 255, 255, 255), 0.15);
  }

  .manual-note {
    padding: 10px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    color: var(--tx-dim);
    text-align: center;
    letter-spacing: 0.04em;
  }

  /* ── Animations ── */
  @keyframes authorizedPulse {
    0%, 100% { box-shadow: 0 0 10px rgba(var(--wr), 0.15); }
    50%       { box-shadow: 0 0 20px rgba(var(--wr), 0.35); }
  }

  @keyframes weaponPulse {
    from { box-shadow: 0 0 6px rgba(var(--wr), 0.3); }
    to   { box-shadow: 0 0 18px rgba(var(--wr), 0.7); }
  }

  @keyframes muzzleFlash {
    0%   { background: rgba(var(--wr), 0.55); border-color: var(--wc); box-shadow: 0 0 28px rgba(var(--wr), 0.7); }
    40%  { background: rgba(var(--wr), 0.18); border-color: rgba(var(--wr), 0.6); box-shadow: 0 0 14px rgba(var(--wr), 0.35); }
    100% { background: rgba(var(--wr), 0.06); border-color: rgba(var(--wr), 0.25); box-shadow: none; }
  }

  @keyframes critFlicker {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
</style>
