<script lang="ts">
  import { onMount } from "svelte";

  export let fullConfig: Record<string, any>;
  export let damageModel: Record<string, any>;

  const DAMAGE_SUBSYSTEMS = [
    "propulsion", "rcs", "weapons", "sensors", "reactor", "life_support",
  ] as const;

  // ── Computed stats ────────────────────────────────────────────────────────────
  $: dryMass   = fullConfig.mass?.dry_mass ?? 0;
  $: fuel      = fullConfig.mass?.max_fuel ?? 0;
  $: wetMass   = dryMass + fuel;
  $: thrust    = fullConfig.systems?.propulsion?.max_thrust ?? 0;   // kN
  $: isp       = fullConfig.systems?.propulsion?.isp ?? 0;
  $: deltaV    = isp > 0 && wetMass > dryMass && dryMass > 0
    ? Math.round(isp * 9.81 * Math.log(wetMass / dryMass))
    : 0;
  $: maxAccelMs2 = thrust > 0 && wetMass > 0 ? (thrust * 1000) / wetMass : 0;
  $: maxAccelG   = maxAccelMs2 / 9.81;
  $: railguns  = fullConfig.systems?.combat?.railguns ?? 0;
  $: pdcs      = fullConfig.systems?.combat?.pdcs ?? 0;
  $: torpedoes = fullConfig.systems?.combat?.torpedoes ?? 0;
  $: avgArmor  = (() => {
    const sections = Object.values(fullConfig.armor ?? {}) as any[];
    if (!sections.length) return 0;
    return sections.reduce((sum: number, s: any) => sum + (s.thickness_cm ?? 0), 0) / sections.length;
  })();

  // ── Sync damage model from fullConfig when class changes ─────────────────────
  let lastClassId = "";
  $: {
    const classId = fullConfig.class_id ?? "";
    if (classId !== lastClassId) {
      lastClassId = classId;
      initDamageModel();
    }
  }

  function initDamageModel() {
    const src = fullConfig.damage_model ?? {};
    const dm: Record<string, any> = {};
    for (const sub of DAMAGE_SUBSYSTEMS) {
      dm[sub] = {
        max_health:        src[sub]?.max_health        ?? 100,
        criticality:       src[sub]?.criticality       ?? 3,
        failure_threshold: src[sub]?.failure_threshold ?? 0.2,
      };
    }
    damageModel = dm;
  }

  onMount(initDamageModel);

  function updateDamage(subsystem: string, field: string, e: Event) {
    const val = parseFloat((e.target as HTMLInputElement).value) || 0;
    damageModel = {
      ...damageModel,
      [subsystem]: { ...(damageModel[subsystem] ?? {}), [field]: val },
    };
  }

  function fmt(n: number, decimals = 0): string {
    return n.toLocaleString("en-US", { maximumFractionDigits: decimals });
  }
</script>

<div class="preview-editor">
  <div class="section-title">PREVIEW</div>

  <!-- Computed stats -->
  <div class="stats-grid">
    <div class="stat-block">
      <div class="stat-label">WET MASS</div>
      <div class="stat-value">{fmt(wetMass)} kg</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">DRY MASS</div>
      <div class="stat-value">{fmt(dryMass)} kg</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">FUEL</div>
      <div class="stat-value">{fmt(fuel)} kg</div>
    </div>
    <div class="stat-block highlight">
      <div class="stat-label">DELTA-V</div>
      <div class="stat-value">{fmt(deltaV)} m/s</div>
    </div>
    <div class="stat-block highlight">
      <div class="stat-label">MAX ACCEL</div>
      <div class="stat-value">{maxAccelG.toFixed(2)} g</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">AVG ARMOR</div>
      <div class="stat-value">{avgArmor.toFixed(1)} cm</div>
    </div>
  </div>

  <!-- Armament summary -->
  <div class="armament-row">
    <span class="arm-item" title="Railguns">⬡ {railguns} RG</span>
    <span class="arm-item" title="PDCs">● {pdcs} PDC</span>
    <span class="arm-item" title="Torpedo tubes">◈ {torpedoes} TRP</span>
  </div>

  <!-- Damage model -->
  <div class="section-title" style="margin-top: var(--space-xs)">DAMAGE MODEL</div>

  <div class="damage-table">
    <div class="damage-header">
      <span>System</span>
      <span>Max HP</span>
      <span>Crit</span>
      <span>Fail %</span>
    </div>
    {#each DAMAGE_SUBSYSTEMS as sub}
      {@const dm = damageModel[sub] ?? { max_health: 100, criticality: 3, failure_threshold: 0.2 }}
      <div class="damage-row">
        <span class="subsys-label">{sub.replace(/_/g, " ")}</span>
        <input
          type="number"
          class="dm-input"
          value={dm.max_health}
          min="1"
          step="10"
          on:change={(e) => updateDamage(sub, "max_health", e)}
        />
        <input
          type="number"
          class="dm-input"
          value={dm.criticality}
          min="0"
          max="10"
          step="0.5"
          on:change={(e) => updateDamage(sub, "criticality", e)}
        />
        <input
          type="number"
          class="dm-input"
          value={dm.failure_threshold}
          min="0"
          max="1"
          step="0.05"
          on:change={(e) => updateDamage(sub, "failure_threshold", e)}
        />
      </div>
    {/each}
  </div>
</div>

<style>
  .preview-editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
    overflow-y: auto;
    padding-right: 2px;
  }

  .section-title {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--tier-accent, var(--text-secondary));
    padding: 4px 0;
    border-bottom: 1px solid var(--border-default);
  }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
  }

  .stat-block {
    border: 1px solid var(--border-default);
    border-radius: 3px;
    padding: 5px 8px;
    background: var(--bg-panel);
  }

  .stat-block.highlight {
    border-color: rgba(var(--tier-accent-rgb, 68,136,255), 0.5);
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.06);
  }

  .stat-label {
    font-family: var(--font-mono);
    font-size: 0.55rem;
    color: var(--text-dim);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .stat-value {
    font-family: var(--font-mono);
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-top: 2px;
  }

  .stat-block.highlight .stat-value {
    color: var(--tier-accent, var(--hud-primary));
  }

  .armament-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .arm-item {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-secondary);
    background: var(--bg-panel);
    border: 1px solid var(--border-default);
    border-radius: 3px;
    padding: 3px 8px;
  }

  /* Damage model */
  .damage-table {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
  }

  .damage-header,
  .damage-row {
    display: grid;
    grid-template-columns: 1fr 60px 50px 55px;
    align-items: center;
    gap: 4px;
  }

  .damage-header {
    color: var(--text-dim);
    font-size: 0.55rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border-default);
    padding-bottom: 2px;
  }

  .damage-row { padding: 2px 0; }

  .subsys-label {
    color: var(--text-secondary);
    text-transform: capitalize;
  }

  .dm-input {
    background: var(--bg-input, rgba(255,255,255,0.04));
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.65rem;
    padding: 2px 4px;
    width: 100%;
    box-sizing: border-box;
  }

  .dm-input:focus {
    outline: none;
    border-color: var(--tier-accent, var(--hud-primary));
  }
</style>
