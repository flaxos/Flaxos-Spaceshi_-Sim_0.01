<script lang="ts">
  /**
   * AttitudeIndicator — SVG artificial horizon (roll + pitch) with heading readout.
   *
   * Mirrors prototype design_reference_v2 (lines 569-609):
   *   - Dark sky/ground halves, rotated by `roll`, shifted by `pitch`.
   *   - Pitch ladder labels at ±10°, ±20°.
   *   - Fixed yellow reticle (waterline + dot) in front of the rotating horizon.
   *   - Roll pointer (yellow tick) rotated with roll.
   *   - Heading readout (3-digit padded) below the dial.
   *
   * Props:
   *   heading: yaw in degrees (0..360)
   *   pitch:   degrees above horizon (+ up, − down)
   *   roll:    degrees (+ starboard-down, − port-down)
   *   size:    px (default 120)
   */
  export let heading: number = 0;
  export let pitch: number = 0;
  export let roll: number = 0;
  export let size: number = 120;

  $: c = size / 2;
  $: pitchPx = (pitch * size) / 90;
  $: groundY = c - pitchPx;
  $: hdgLabel = String(Math.round(((heading % 360) + 360) % 360)).padStart(3, "0");
  $: clipId = `aci-${size}-${Math.floor(Math.random() * 100000)}`;

  // Pitch ladder entries
  const LADDER = [-20, -10, 10, 20];
</script>

<svg class="attitude-indicator" width={size} height={size} viewBox="0 0 {size} {size}" role="img" aria-label="Attitude indicator">
  <defs>
    <clipPath id={clipId}>
      <circle cx={c} cy={c} r={c - 4} />
    </clipPath>
  </defs>

  <g clip-path="url(#{clipId})">
    <!-- Sky background -->
    <rect x="0" y="0" width={size} height={size} fill="#0a1528" />

    <!-- Rolling horizon group -->
    <g transform="rotate({roll} {c} {c})">
      <!-- Ground -->
      <rect x={-size} y={groundY} width={size * 3} height={size * 2} fill="#1a0e00" />
      <!-- Horizon line -->
      <rect x={-size} y={groundY - 1} width={size * 3} height="2" fill="#555" />
      <!-- Pitch ladder -->
      {#each LADDER as p}
        <g transform="translate(0, {(-p * size) / 90 + pitchPx})">
          <line x1={c - 15} y1="0" x2={c + 15} y2="0" stroke="#ffffff44" stroke-width="1" />
          <text x={c + 18} y="4" font-size="7" fill="#ffffff66" font-family="var(--font-mono)">{Math.abs(p)}</text>
        </g>
      {/each}
    </g>

    <!-- Fixed reticle (yellow waterline) -->
    <line x1={c - 30} y1={c} x2={c - 10} y2={c} stroke="#ffcc00" stroke-width="2" />
    <line x1={c + 10} y1={c} x2={c + 30} y2={c} stroke="#ffcc00" stroke-width="2" />
    <line x1={c} y1={c - 4} x2={c} y2={c + 4} stroke="#ffcc00" stroke-width="1.5" />

    <!-- Roll pointer -->
    <g transform="rotate({roll} {c} {c})">
      <line x1={c} y1="6" x2={c} y2="14" stroke="#ffcc00" stroke-width="1.5" />
    </g>
  </g>

  <!-- Outer ring -->
  <circle cx={c} cy={c} r={c - 4} fill="none" stroke="var(--bd-active)" stroke-width="1.5" />

  <!-- Heading readout -->
  <text x={c} y={size - 3} text-anchor="middle" font-size="7" fill="var(--tx-dim)" font-family="var(--font-mono)">
    {hdgLabel}°
  </text>
</svg>

<style>
  .attitude-indicator {
    flex-shrink: 0;
    display: block;
  }
</style>
