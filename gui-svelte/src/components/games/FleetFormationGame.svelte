<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  const FORMATIONS = {
    wedge: [
      { x: 180, y: 60 },
      { x: 120, y: 130 },
      { x: 240, y: 130 },
      { x: 180, y: 200 },
    ],
    line: [
      { x: 80, y: 140 },
      { x: 150, y: 140 },
      { x: 220, y: 140 },
      { x: 290, y: 140 },
    ],
    diamond: [
      { x: 180, y: 60 },
      { x: 110, y: 140 },
      { x: 250, y: 140 },
      { x: 180, y: 220 },
    ],
  } as const;

  type FormationKey = keyof typeof FORMATIONS;

  interface ShipToken {
    id: string;
    x: number;
    y: number;
    slot: number;
  }

  let board: HTMLDivElement | null = null;
  let formation: FormationKey = "wedge";
  let ships: ShipToken[] = [];
  let draggingId = "";
  let offsetX = 0;
  let offsetY = 0;
  let solvedSent = false;

  onMount(() => {
    resetBoard();
  });

  function resetBoard() {
    ships = [
      { id: "A", x: 24, y: 28, slot: -1 },
      { id: "B", x: 24, y: 82, slot: -1 },
      { id: "C", x: 24, y: 136, slot: -1 },
      { id: "D", x: 24, y: 190, slot: -1 },
    ];
    solvedSent = false;
  }

  function pointerDown(event: PointerEvent, shipId: string) {
    const token = ships.find((ship) => ship.id === shipId);
    if (!token || !board) return;
    const rect = board.getBoundingClientRect();
    draggingId = shipId;
    offsetX = event.clientX - rect.left - token.x;
    offsetY = event.clientY - rect.top - token.y;
  }

  function pointerMove(event: PointerEvent) {
    if (!draggingId || !board) return;
    const rect = board.getBoundingClientRect();
    ships = ships.map((ship) => ship.id === draggingId
      ? { ...ship, x: event.clientX - rect.left - offsetX, y: event.clientY - rect.top - offsetY, slot: -1 }
      : ship);
  }

  function pointerUp() {
    if (!draggingId) return;
    const slots = FORMATIONS[formation];
    ships = ships.map((ship) => {
      if (ship.id !== draggingId) return ship;
      let bestSlot = -1;
      let bestDistance = Number.POSITIVE_INFINITY;
      slots.forEach((slot, index) => {
        const distance = Math.hypot(ship.x - slot.x, ship.y - slot.y);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestSlot = index;
        }
      });
      if (bestSlot >= 0 && bestDistance < 50) {
        return { ...ship, x: slots[bestSlot].x, y: slots[bestSlot].y, slot: bestSlot };
      }
      return ship;
    });
    draggingId = "";
    checkSolved();
  }

  async function checkSolved() {
    const solved = ships.every((ship) => ship.slot >= 0) && new Set(ships.map((ship) => ship.slot)).size === ships.length;
    if (!solved || solvedSent) return;
    solvedSent = true;
    await wsClient.sendShipCommand("fleet_form", { formation });
  }
</script>

<svelte:window on:pointermove={pointerMove} on:pointerup={pointerUp} />

<Panel title="Formation Puzzle" domain="weapons" priority="secondary" className="fleet-formation-game">
  <div class="shell">
    <div class="toolbar">
      <select bind:value={formation} on:change={resetBoard}>
        <option value="wedge">WEDGE</option>
        <option value="line">LINE</option>
        <option value="diamond">DIAMOND</option>
      </select>
      <button type="button" on:click={resetBoard}>RESET</button>
    </div>

    <div class="board" bind:this={board}>
      {#each FORMATIONS[formation] as slot}
        <div class="slot" style={`left:${slot.x}px; top:${slot.y}px;`}></div>
      {/each}
      {#each ships as ship}
        <button
          class="ship-token"
          type="button"
          style={`left:${ship.x}px; top:${ship.y}px;`}
          on:pointerdown={(event) => pointerDown(event, ship.id)}
        >
          {ship.id}
        </button>
      {/each}
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: 10px;
    padding: var(--space-sm);
  }

  .toolbar {
    display: flex;
    gap: 8px;
  }

  select,
  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  .board {
    position: relative;
    height: 280px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background:
      linear-gradient(transparent 23px, rgba(255,255,255,0.04) 24px),
      linear-gradient(90deg, transparent 23px, rgba(255,255,255,0.04) 24px),
      #0b1219;
    background-size: 24px 24px;
    overflow: hidden;
  }

  .slot,
  .ship-token {
    position: absolute;
    width: 34px;
    height: 34px;
    transform: translate(-50%, -50%);
    border-radius: 50%;
  }

  .slot {
    border: 2px dashed rgba(0, 170, 255, 0.45);
    background: rgba(0, 170, 255, 0.06);
  }

  .ship-token {
    border: 1px solid rgba(255, 212, 107, 0.45);
    background: rgba(255, 212, 107, 0.14);
    color: #ffd46b;
    font-weight: 700;
    cursor: grab;
  }
</style>
