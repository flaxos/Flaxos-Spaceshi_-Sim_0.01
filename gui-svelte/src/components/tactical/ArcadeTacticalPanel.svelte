<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import TargetingLockGame from "../games/TargetingLockGame.svelte";
  import WeaponsChargeGame from "../games/WeaponsChargeGame.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getBestWeaponSolution,
    getLockedTargetId,
    getTargetingSummary,
    getWeaponMounts,
    toNumber,
    type WeaponMountState,
  } from "./tacticalData.js";
  import { fireRailgun, launchDirectMunition } from "./tacticalActions.js";

  // Arcade tactical station:
  //   - No target locked  → TargetingLockGame (reticle mini-game)
  //   - Target locked     → WeaponsChargeGame (timing mini-game)
  //
  // The games themselves are passive skill visuals. The FIRE button below each
  // is the actual fire trigger. It is armed only when the preconditions for a
  // real shot are met (locked, ammo, solution confidence >= 0.38 for railguns).
  // The player's interaction with the game does not gate firing — it just makes
  // the arcade tier feel tactile. Scoring and gating stay server-authoritative.

  $: ship = extractShipState($gameState);
  $: targeting = getTargetingSummary(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: effectiveTarget = $selectedTacticalTargetId || lockedTargetId;
  $: hasLock = targeting.lockState === "locked" && Boolean(lockedTargetId);
  $: mounts = getWeaponMounts(ship);
  $: solution = getBestWeaponSolution(ship);
  $: solutionConfidence = clamp01(toNumber(solution.confidence, targeting.lockQuality));
  $: bestWeapon = pickBestWeapon(mounts, solutionConfidence);
  $: firing = false;
  $: fireHint = buildFireHint(hasLock, bestWeapon, solutionConfidence);

  function clamp01(n: number): number {
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  /**
   * Pick the best weapon available to fire right now.
   *   Priority: ready railgun w/ strong solution → missile → torpedo.
   * Returns null if nothing is fireable.
   */
  function pickBestWeapon(
    all: WeaponMountState[],
    confidence: number,
  ): WeaponMountState | null {
    const railgun = all.find(
      (m) => m.weaponType === "railgun" && m.enabled && m.ammo > 0 && m.ready && confidence >= 0.38,
    );
    if (railgun) return railgun;

    const missile = all.find(
      (m) => m.weaponType === "missile" && m.enabled && m.ammo > 0,
    );
    if (missile) return missile;

    const torpedo = all.find(
      (m) => m.weaponType === "torpedo" && m.enabled && m.ammo > 0,
    );
    if (torpedo) return torpedo;

    return null;
  }

  function buildFireHint(
    locked: boolean,
    weapon: WeaponMountState | null,
    confidence: number,
  ): string {
    if (!locked) return "Lock a target first";
    if (!weapon) return "No weapons available";
    if (weapon.weaponType === "railgun") {
      if (!weapon.ready) return `Railgun charging (${Math.round(weapon.charge * 100)}%)`;
      if (confidence < 0.38) return `Solution too weak (${Math.round(confidence * 100)}%)`;
      return `Fire railgun — ${Math.round(confidence * 100)}% solution`;
    }
    if (weapon.weaponType === "missile") return "Launch missile";
    if (weapon.weaponType === "torpedo") return "Launch torpedo";
    return "Weapon ready";
  }

  async function doFire() {
    if (firing) return;
    if (!hasLock || !bestWeapon) return;
    firing = true;
    try {
      if (bestWeapon.weaponType === "railgun") {
        await fireRailgun({ mountId: bestWeapon.id, targetId: effectiveTarget || undefined });
      } else if (bestWeapon.weaponType === "torpedo" || bestWeapon.weaponType === "missile") {
        await launchDirectMunition(bestWeapon.weaponType, {
          targetId: effectiveTarget || undefined,
          profile: "direct",
        });
      }
    } finally {
      firing = false;
    }
  }

  $: fireArmed = hasLock && bestWeapon !== null && !firing;
</script>

<Panel title="Combat Station" domain="weapons" priority="primary">
  <div class="arcade-body">
    {#if !hasLock}
      <div class="stage-label">Acquire target lock</div>
      <TargetingLockGame />
      <div class="status-row">
        <span class="status-label">Lock state</span>
        <span class="status-value" class:warn={!hasLock}>{targeting.lockState.toUpperCase()}</span>
      </div>
    {:else}
      <div class="stage-label">Charge and fire</div>
      <WeaponsChargeGame />
      <div class="status-row">
        <span class="status-label">Weapon</span>
        <span class="status-value">{bestWeapon ? bestWeapon.label : "NONE"}</span>
      </div>
      <div class="status-row">
        <span class="status-label">Solution</span>
        <span class="status-value" class:warn={solutionConfidence < 0.38}>
          {Math.round(solutionConfidence * 100)}%
        </span>
      </div>
    {/if}

    <button
      class="fire-btn"
      class:armed={fireArmed}
      disabled={!fireArmed}
      title={fireHint}
      on:click={() => void doFire()}
    >
      {#if firing}
        FIRING…
      {:else if fireArmed}
        <span class="bullet">●</span> FIRE
        {#if bestWeapon}
          <span class="weapon-chip">{bestWeapon.weaponType.toUpperCase()}</span>
        {/if}
      {:else}
        {fireHint}
      {/if}
    </button>
  </div>
</Panel>

<style>
  .arcade-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    padding: var(--space-xs);
  }

  .stage-label {
    font-family: var(--font-mono);
    font-size: 0.58rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--tx-dim);
  }

  .status-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-family: var(--font-mono);
    font-size: 0.62rem;
  }

  .status-label {
    color: var(--tx-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .status-value {
    color: var(--tx-primary);
    font-weight: 600;
  }

  .status-value.warn {
    color: var(--warn);
  }

  .fire-btn {
    margin-top: 4px;
    padding: 10px;
    background: rgba(30, 30, 48, 0.4);
    border: 1px solid var(--bd-subtle);
    border-radius: 2px;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: not-allowed;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .fire-btn.armed {
    background: rgba(192, 48, 48, 0.2);
    border-color: rgba(232, 48, 48, 0.5);
    color: var(--crit);
    box-shadow: 0 0 18px rgba(232, 48, 48, 0.24);
    cursor: pointer;
  }

  .fire-btn.armed:hover {
    background: rgba(232, 48, 48, 0.3);
    box-shadow: 0 0 24px rgba(232, 48, 48, 0.36);
  }

  .weapon-chip {
    font-size: 0.58rem;
    padding: 1px 6px;
    border: 1px solid currentColor;
    border-radius: 2px;
    letter-spacing: 0.1em;
  }

  .bullet {
    font-size: 0.7em;
  }
</style>
