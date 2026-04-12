<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { extractShipState, getThrusters } from "./helmData.js";

  interface DiagramThruster {
    id: string;
    x: number;
    y: number;
    throttle: number;
  }

  const THRUSTER_LAYOUT: Record<string, { x: number; y: number }> = {
    pitch_up: { x: 76, y: 48 },
    pitch_down: { x: 164, y: 48 },
    pitch_up_aft: { x: 76, y: 264 },
    pitch_down_aft: { x: 164, y: 264 },
    yaw_left: { x: 50, y: 88 },
    yaw_right: { x: 190, y: 88 },
    yaw_left_aft: { x: 50, y: 224 },
    yaw_right_aft: { x: 190, y: 224 },
    roll_cw: { x: 76, y: 146 },
    roll_ccw: { x: 164, y: 146 },
    roll_cw_2: { x: 76, y: 178 },
    roll_ccw_2: { x: 164, y: 178 },
  };

  let feedback = "";

  $: ship = extractShipState($gameState);
  $: thrusters = getThrusters(ship);
  $: interactive = $tier === "manual" || $tier === "raw";
  $: diagramThrusters = thrusters.map((thruster, index) => layoutThruster(thruster.id, thruster.throttle, index));

  function layoutThruster(id: string, throttle: number, index: number): DiagramThruster {
    const fallbackX = 58 + (index % 4) * 42;
    const fallbackY = 70 + Math.floor(index / 4) * 60;
    const point = THRUSTER_LAYOUT[id] ?? { x: fallbackX, y: fallbackY };
    return { id, throttle, ...point };
  }

  async function pulseThruster(thrusterId: string, active: boolean) {
    if (!interactive) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("rcs_fire_thruster", {
        thruster_id: thrusterId,
        throttle: active ? 0 : 1,
        duration: active ? 0 : 0.3,
      });
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Thruster command failed";
    }
  }

  function onThrusterKeydown(event: KeyboardEvent, thrusterId: string, active: boolean) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    void pulseThruster(thrusterId, active);
  }
</script>

<Panel title="Thruster Map" domain="helm" priority="secondary" className="rcs-thruster-panel">
  <div class="shell">
    <svg viewBox="0 0 240 320" class="diagram" aria-label="RCS thruster display">
      <path d="M120 24 L168 72 L168 248 L120 296 L72 248 L72 72 Z" class="hull" />
      <rect x="106" y="48" width="28" height="224" rx="10" class="spine" />

      {#each diagramThrusters as thruster}
        <g class="thruster-group">
          <a
            href={`#${thruster.id}`}
            aria-label={`Pulse ${thruster.id}`}
            on:click|preventDefault={() => pulseThruster(thruster.id, thruster.throttle > 0.05)}
            on:keydown={(event) => onThrusterKeydown(event, thruster.id, thruster.throttle > 0.05)}
          >
            <circle
              class:active={thruster.throttle > 0.05}
              class:interactive={interactive}
              cx={thruster.x}
              cy={thruster.y}
              r="10"
            />
          </a>
          <text x={thruster.x} y={thruster.y + 23}>{thruster.id}</text>
        </g>
      {/each}
    </svg>

    <div class="legend">
      <span>Active thrusters: {diagramThrusters.filter((thruster) => thruster.throttle > 0.05).length}</span>
      <span>{interactive ? "Click any thruster to pulse it." : "Live telemetry only."}</span>
    </div>

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

  .diagram {
    width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: radial-gradient(circle at center, rgba(255, 255, 255, 0.04), transparent 65%), #0b1017;
  }

  .hull,
  .spine {
    fill: rgba(255, 255, 255, 0.06);
    stroke: rgba(255, 255, 255, 0.18);
  }

  circle {
    fill: rgba(0, 170, 255, 0.16);
    stroke: rgba(0, 170, 255, 0.45);
    transition: fill var(--transition-fast), transform var(--transition-fast);
  }

  circle.active {
    fill: rgba(255, 170, 0, 0.8);
    stroke: rgba(255, 170, 0, 1);
    filter: drop-shadow(0 0 8px rgba(255, 170, 0, 0.55));
  }

  circle.interactive {
    cursor: pointer;
  }

  circle.interactive:hover {
    transform: scale(1.05);
  }

  text {
    fill: rgba(255, 255, 255, 0.62);
    font: 7px "JetBrains Mono", monospace;
    text-anchor: middle;
  }

  .legend,
  .feedback {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }
</style>
