<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getOpsShip, getRepairTargets } from "../ops/opsData.js";

  type CellType = "line" | "corner" | "tee" | "blocked";
  interface Cell {
    type: CellType;
    rotation: number;
  }

  const SIZE = 4;
  const START = { x: 0, y: 1 };
  const END = { x: 3, y: 2 };

  let grid: Cell[][] = [];
  let solving = false;
  let solvedTarget = "";
  let feedback = "";

  $: ship = getOpsShip($gameState);
  $: targets = getRepairTargets(ship);
  $: activeTarget = targets[0]?.id ?? "";
  $: if (!grid.length || solvedTarget !== activeTarget) resetPuzzle(activeTarget);

  function openings(cell: Cell): boolean[] {
    if (cell.type === "blocked") return [false, false, false, false];
    const variants: Record<CellType, boolean[][]> = {
      line: [
        [true, false, true, false],
        [false, true, false, true],
        [true, false, true, false],
        [false, true, false, true],
      ],
      corner: [
        [true, true, false, false],
        [false, true, true, false],
        [false, false, true, true],
        [true, false, false, true],
      ],
      tee: [
        [true, true, false, true],
        [true, true, true, false],
        [false, true, true, true],
        [true, false, true, true],
      ],
      blocked: [[false, false, false, false]],
    };
    return variants[cell.type][cell.rotation % variants[cell.type].length];
  }

  function resetPuzzle(targetId: string) {
    solvedTarget = targetId;
    feedback = "";
    solving = false;
    const seed: Cell[][] = [
      [{ type: "line", rotation: 1 }, { type: "corner", rotation: 1 }, { type: "line", rotation: 1 }, { type: "corner", rotation: 2 }],
      [{ type: "line", rotation: 1 }, { type: "blocked", rotation: 0 }, { type: "tee", rotation: 2 }, { type: "line", rotation: 0 }],
      [{ type: "corner", rotation: 0 }, { type: "line", rotation: 1 }, { type: "corner", rotation: 3 }, { type: "line", rotation: 0 }],
      [{ type: "blocked", rotation: 0 }, { type: "corner", rotation: 0 }, { type: "line", rotation: 1 }, { type: "corner", rotation: 3 }],
    ];
    grid = seed.map((row) => row.map((cell) => ({ ...cell, rotation: cell.type === "blocked" ? 0 : Math.floor(Math.random() * 4) })));
  }

  function rotateCell(x: number, y: number) {
    const cell = grid[y][x];
    if (cell.type === "blocked") return;
    grid = grid.map((row, rowIndex) =>
      row.map((entry, colIndex) =>
        rowIndex === y && colIndex === x
          ? { ...entry, rotation: (entry.rotation + 1) % 4 }
          : entry,
      ),
    );
    if (isSolved()) {
      solving = true;
      void dispatchRepair();
    }
  }

  function isSolved(): boolean {
    const queue = [[START.x, START.y]];
    const visited = new Set<string>();
    const dirs = [
      [0, -1, 2],
      [1, 0, 3],
      [0, 1, 0],
      [-1, 0, 1],
    ];

    while (queue.length) {
      const [x, y] = queue.shift()!;
      const key = `${x},${y}`;
      if (visited.has(key)) continue;
      visited.add(key);
      if (x === END.x && y === END.y) return true;

      const cell = grid[y]?.[x];
      if (!cell) continue;
      const open = openings(cell);
      dirs.forEach(([dx, dy, opposite], index) => {
        if (!open[index]) return;
        const nx = x + dx;
        const ny = y + dy;
        const next = grid[ny]?.[nx];
        if (!next) return;
        if (!openings(next)[opposite]) return;
        queue.push([nx, ny]);
      });
    }
    return false;
  }

  async function dispatchRepair() {
    if (!activeTarget) return;
    try {
      await wsClient.sendShipCommand("dispatch_repair", { subsystem: activeTarget });
      feedback = `Repair dispatched to ${activeTarget}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Dispatch failed";
    } finally {
      solving = false;
    }
  }

  function symbol(cell: Cell): string {
    if (cell.type === "blocked") return "■";
    if (cell.type === "line") return cell.rotation % 2 === 0 ? "│" : "─";
    if (cell.type === "corner") return ["└", "┌", "┐", "┘"][cell.rotation % 4];
    return ["┴", "├", "┬", "┤"][cell.rotation % 4];
  }
</script>

<Panel title="Damage Control" domain="power" priority="primary" className="damage-control-game">
  <div class="shell">
    <div class="header">
      <span>Route power from reactor to damaged system</span>
      <strong>{activeTarget ? activeTarget.toUpperCase() : "NO TARGET"}</strong>
    </div>
    <div class="grid">
      {#each grid as row, y}
        {#each row as cell, x}
          <button
            type="button"
            class="cell"
            class:blocked={cell.type === "blocked"}
            class:start={x === START.x && y === START.y}
            class:end={x === END.x && y === END.y}
            on:click={() => rotateCell(x, y)}
          >
            {symbol(cell)}
          </button>
        {/each}
      {/each}
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

  .header,
  .feedback {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
  }

  .cell {
    aspect-ratio: 1;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 1.4rem;
  }

  .cell.start {
    border-color: rgba(0, 255, 136, 0.45);
  }

  .cell.end {
    border-color: rgba(68, 136, 255, 0.45);
  }

  .cell.blocked {
    opacity: 0.35;
  }

  span,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .feedback {
    color: var(--status-info);
  }
</style>
