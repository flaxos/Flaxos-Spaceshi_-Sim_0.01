<script lang="ts">
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getBestWeaponSolution,
    getLauncherInventory,
    getLockedTargetId,
    getTargetingSummary,
    getWeaponMounts,
    toNumber,
    type WeaponMountState,
  } from "./tacticalData.js";
  import { fireRailgun, launchDirectMunition } from "./tacticalActions.js";

  let firingIds = new Set<string>();
  // Track mounts that just completed a fire command for the muzzle-flash animation.
  let justFiredIds = new Set<string>();
  let justFiredTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  $: ship = extractShipState($gameState);
  $: mounts = getWeaponMounts(ship);
  $: targeting = getTargetingSummary(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: effectiveTarget = $selectedTacticalTargetId || lockedTargetId;
  $: solution = getBestWeaponSolution(ship);
  $: solutionConfidence = clamp01(toNumber(solution.confidence, targeting.lockQuality));
  $: launchers = getLauncherInventory(ship);

  $: displayMounts = buildDisplayMounts(mounts, launchers);

  function clamp01(n: number): number {
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  function buildDisplayMounts(
    existing: WeaponMountState[],
    inv: ReturnType<typeof getLauncherInventory>,
  ): WeaponMountState[] {
    const list = [...existing];
    const hasType = (t: WeaponMountState["weaponType"]) => list.some((mount) => mount.weaponType === t);

    const torpLoaded = toNumber(inv.torpedoes.loaded, Number.NaN);
    const torpCap = toNumber(inv.torpedoes.capacity, toNumber(inv.torpedoes.max, Number.NaN));
    if (!hasType("torpedo") && Number.isFinite(torpLoaded) && torpLoaded > 0) {
      list.push(syntheticLauncher("torpedo", "TORPEDO BAY", torpLoaded, torpCap));
    }

    const missileLoaded = toNumber(inv.missiles.loaded, Number.NaN);
    const missileCap = toNumber(inv.missiles.capacity, toNumber(inv.missiles.max, Number.NaN));
    if (!hasType("missile") && Number.isFinite(missileLoaded) && missileLoaded > 0) {
      list.push(syntheticLauncher("missile", "MISSILE BAY", missileLoaded, missileCap));
    }

    return list;
  }

  function syntheticLauncher(
    type: "torpedo" | "missile",
    label: string,
    loaded: number,
    cap: number,
  ): WeaponMountState {
    return {
      id: type === "torpedo" ? "torpedo_bay" : "missile_bay",
      label,
      type,
      weaponType: type,
      ammo: loaded,
      ammoCapacity: Number.isFinite(cap) ? cap : loaded,
      ready: loaded > 0,
      enabled: true,
      charge: 1,
      cooldown: 0,
      reloading: false,
      reloadProgress: 0,
      reloadTime: 0,
      chargeState: "idle",
      status: loaded > 0 ? "loaded" : "empty",
      range: 0,
    };
  }

  function ammoPct(mount: WeaponMountState): number {
    if (mount.ammoCapacity <= 0) return 100;
    return Math.max(0, Math.min(100, (mount.ammo / mount.ammoCapacity) * 100));
  }

  function statusDotColor(mount: WeaponMountState): string {
    const status = mount.status.toLowerCase();
    if (mount.ready || status === "loaded" || status === "ready") return "var(--nom)";
    if (mount.reloading || status === "reloading") return "var(--warn)";
    if (status === "empty" || mount.ammo <= 0) return "var(--crit)";
    return "var(--tx-dim)";
  }

  function statusTextColor(mount: WeaponMountState): string {
    const status = mount.status.toLowerCase();
    if (status === "ready" || status === "loaded") return "var(--nom)";
    if (status === "reloading") return "var(--warn)";
    if (status === "empty") return "var(--crit)";
    return "var(--tx-dim)";
  }

  function ammoColor(pct: number): string {
    if (pct > 60) return "var(--nom)";
    if (pct > 30) return "var(--warn)";
    return "var(--crit)";
  }

  function rowBgTint(mount: WeaponMountState): string {
    if (mount.weaponType === "railgun") return "rgba(192, 48, 48, 0.04)";
    if (mount.weaponType === "torpedo") return "rgba(240, 152, 32, 0.03)";
    if (mount.weaponType === "missile") return "rgba(239, 160, 32, 0.025)";
    return "transparent";
  }

  function canFire(mount: WeaponMountState): boolean {
    if (!mount.enabled || mount.ammo <= 0) return false;
    if (mount.weaponType === "railgun") {
      return mount.ready && targeting.lockState === "locked" && solutionConfidence >= 0.38 && !firingIds.has(mount.id);
    }
    if (mount.weaponType === "torpedo" || mount.weaponType === "missile") {
      return targeting.lockState === "locked" && !firingIds.has(mount.id);
    }
    return false;
  }

  function fireTitle(mount: WeaponMountState): string {
    if (mount.ammo <= 0) return "No ammunition";
    if (!mount.enabled) return "Weapon disabled";
    if (targeting.lockState !== "locked") return "Target not locked";
    if (mount.weaponType === "railgun") {
      if (!mount.ready) {
        const chargePct = Math.round(mount.charge * 100);
        return chargePct < 100 ? `Charging (${chargePct}%)` : "Not ready";
      }
      if (solutionConfidence < 0.38) {
        return `Solution too weak (${Math.round(solutionConfidence * 100)}%)`;
      }
      return "Fire railgun";
    }
    if (mount.weaponType === "torpedo") return "Launch torpedo";
    if (mount.weaponType === "missile") return "Launch missile";
    return "PDC auto-engages";
  }

  async function fire(mount: WeaponMountState) {
    if (!canFire(mount)) return;
    firingIds = new Set(firingIds).add(mount.id);
    try {
      if (mount.weaponType === "railgun") {
        await fireRailgun({ mountId: mount.id, targetId: effectiveTarget || undefined });
      } else if (mount.weaponType === "torpedo") {
        await launchDirectMunition("torpedo", { targetId: effectiveTarget || undefined });
      } else if (mount.weaponType === "missile") {
        await launchDirectMunition("missile", { targetId: effectiveTarget || undefined });
      }
      // Trigger muzzle-flash on the row after a successful fire
      clearTimeout(justFiredTimers[mount.id]);
      justFiredIds = new Set(justFiredIds).add(mount.id);
      justFiredTimers[mount.id] = setTimeout(() => {
        const next = new Set(justFiredIds);
        next.delete(mount.id);
        justFiredIds = next;
      }, 650);
    } finally {
      const next = new Set(firingIds);
      next.delete(mount.id);
      firingIds = next;
    }
  }
</script>

<div class="shell">
  {#if displayMounts.length === 0}
    <div class="empty">No weapons available.</div>
  {:else}
    {#each displayMounts as mount (mount.id)}
      {@const ammoPercentage = ammoPct(mount)}
      {@const status = mount.status.toLowerCase()}
      {@const isRailgun = mount.weaponType === "railgun"}
      {@const isPdc = mount.weaponType === "pdc"}
      {@const isLauncher = mount.weaponType === "torpedo" || mount.weaponType === "missile"}
      {@const showFire = isRailgun || isLauncher}
      {@const allowed = canFire(mount)}
      {@const isFiring = firingIds.has(mount.id)}
      {@const justFired = justFiredIds.has(mount.id)}
      <div
        class="row"
        class:just-fired={justFired}
        class:is-firing={isFiring}
        style="background: {rowBgTint(mount)};"
      >
        <div class="head">
          <div class="name">
            <span
              class="dot"
              class:dot-fire={isFiring || justFired}
              class:dot-reload={mount.reloading}
              style="background: {isFiring || justFired ? '#fff' : statusDotColor(mount)};"
              aria-hidden="true"
            ></span>
            <span class="lbl">{mount.label}</span>
          </div>
          <div class="status">
            {#if isPdc}
              <span class="auto-badge">AUTO</span>
            {/if}
            <span
              class="status-txt"
              class:pulse={mount.reloading || status === "reloading"}
              style="color: {statusTextColor(mount)};"
            >{mount.status.toUpperCase()}</span>
          </div>
        </div>

        <div class="ammo-row">
          <div class="bar-track" class:thick={isRailgun}>
            <div
              class="bar-fill"
              style="width: {ammoPercentage}%; background: {ammoColor(ammoPercentage)}; box-shadow: {ammoPercentage > 60 ? `0 0 6px ${ammoColor(ammoPercentage)}55` : 'none'};"
            ></div>
          </div>
          <span class="ammo-count">{mount.ammo}/{mount.ammoCapacity || mount.ammo}</span>
        </div>

        {#if mount.reloading || status === "reloading"}
          <div class="reload-row">
            <span class="reload-label">RELOAD</span>
            <div class="reload-track">
              <div class="reload-fill" style="width: {Math.round(mount.reloadProgress * 100)}%;"></div>
            </div>
            <span class="reload-pct">{Math.round(mount.reloadProgress * 100)}%</span>
          </div>
        {/if}

        {#if showFire}
          <button
            class="fire-btn"
            class:armed={allowed}
            class:is-firing={isFiring}
            disabled={!allowed}
            title={fireTitle(mount)}
            on:click={() => void fire(mount)}
          >
            {#if isFiring}
              <span class="bullet">●</span> FIRING…
            {:else if allowed}
              <span class="bullet">●</span>
              {isRailgun
                ? `FIRE — ${Math.round(solutionConfidence * 100)}% SOL`
                : mount.weaponType === "torpedo"
                  ? "LAUNCH TORPEDO"
                  : "LAUNCH MISSILE"}
            {:else}
              <span class="bullet">○</span>
              {targeting.lockState !== "locked"
                ? "LOCK REQUIRED"
                : isRailgun
                  ? "SOLUTION REQUIRED"
                  : "NOT READY"}
            {/if}
          </button>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
  }

  .empty {
    padding: 18px;
    text-align: center;
    font-size: var(--font-size-xs);
    color: var(--tx-dim);
    font-family: var(--font-mono);
  }

  .row {
    padding: 8px 10px;
    border-bottom: 1px solid var(--bd-subtle);
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .row:last-child {
    border-bottom: none;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }

  .name {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .lbl {
    font-size: 0.67rem;
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--tx-primary);
    letter-spacing: 0.02em;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .auto-badge {
    font-size: 0.53rem;
    font-family: var(--font-mono);
    color: var(--tx-dim);
    padding: 1px 5px;
    border: 1px solid var(--bd-default);
    border-radius: 2px;
    letter-spacing: 0.08em;
  }

  .status-txt {
    font-size: 0.58rem;
    font-family: var(--font-mono);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .status-txt.pulse {
    animation: pulse 1s ease-in-out infinite;
  }

  .ammo-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .bar-track {
    flex: 1;
    height: 3px;
    background: var(--bg-input);
    border-radius: 1px;
    overflow: hidden;
  }

  .bar-track.thick {
    height: 4px;
  }

  .bar-fill {
    height: 100%;
    transition: width 0.4s ease, background 0.4s ease;
  }

  .ammo-count {
    font-size: 0.6rem;
    font-family: var(--font-mono);
    color: var(--tx-sec);
    min-width: 44px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  /* Muzzle flash on the row */
  .row.just-fired {
    animation: rowFlash 0.6s ease-out forwards;
  }

  .row.is-firing .fire-btn {
    animation: firingPulse 0.4s ease-in-out infinite alternate;
  }

  /* Status dot firing states */
  .dot.dot-fire {
    animation: dotFlash 0.18s ease-in-out infinite;
  }

  .dot.dot-reload {
    animation: pulse 1.2s ease-in-out infinite;
  }

  /* Reload row */
  .reload-row {
    display: grid;
    grid-template-columns: 46px minmax(0, 1fr) 32px;
    gap: 5px;
    align-items: center;
  }

  .reload-label {
    font-size: 0.52rem;
    font-family: var(--font-mono);
    letter-spacing: 0.08em;
    color: var(--warn);
    text-transform: uppercase;
  }

  .reload-pct {
    font-size: 0.55rem;
    font-family: var(--font-mono);
    color: var(--warn);
    text-align: right;
  }

  .reload-track {
    height: 4px;
    background: var(--bg-input);
    border-radius: 2px;
    overflow: hidden;
    border: 1px solid rgba(239, 160, 32, 0.2);
  }

  .reload-fill {
    height: 100%;
    background: var(--warn);
    box-shadow: 0 0 6px rgba(239, 160, 32, 0.5);
    transition: width 0.25s linear;
  }

  .fire-btn {
    margin-top: 2px;
    width: 100%;
    padding: 7px 10px;
    background: rgba(30, 30, 48, 0.4);
    border: 1px solid var(--bd-subtle);
    border-radius: 2px;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: not-allowed;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .fire-btn.armed {
    background: rgba(192, 48, 48, 0.18);
    border-color: rgba(232, 48, 48, 0.4);
    color: var(--crit);
    box-shadow: 0 0 16px rgba(232, 48, 48, 0.22);
    cursor: pointer;
  }

  .fire-btn.armed:hover {
    background: rgba(232, 48, 48, 0.28);
    box-shadow: 0 0 22px rgba(232, 48, 48, 0.32);
  }

  .fire-btn.is-firing {
    border-color: rgba(232, 48, 48, 0.8);
    color: #fff;
    box-shadow: 0 0 20px rgba(232, 48, 48, 0.5);
  }

  .bullet {
    font-size: 0.7em;
    line-height: 1;
  }

  @keyframes rowFlash {
    0%   { background: rgba(232, 48, 48, 0.22) !important; box-shadow: inset 0 0 16px rgba(232, 48, 48, 0.3); }
    50%  { background: rgba(232, 48, 48, 0.08) !important; }
    100% { box-shadow: none; }
  }

  @keyframes firingPulse {
    from { box-shadow: 0 0 8px rgba(232, 48, 48, 0.4); }
    to   { box-shadow: 0 0 20px rgba(232, 48, 48, 0.8); }
  }

  @keyframes dotFlash {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.15; }
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
</style>
