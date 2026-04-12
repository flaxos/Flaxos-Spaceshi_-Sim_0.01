<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  type Filter = "all" | "railgun" | "torpedo" | "missile" | "pdc";

  let filter: Filter = "all";
  let entries: Array<Record<string, unknown>> = [];
  let latestId = 0;
  let pollHandle: number | null = null;

  onMount(() => {
    void poll();
    pollHandle = window.setInterval(() => void poll(), 900);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function poll() {
    try {
      const params: Record<string, unknown> = { since_id: latestId, limit: 50 };
      if (filter !== "all") params.weapon = filter;
      const response = await wsClient.send("get_combat_log", params) as { entries?: Array<Record<string, unknown>>; latest_id?: number };
      if (Array.isArray(response.entries) && response.entries.length > 0) {
        entries = [...entries, ...response.entries].slice(-200);
      }
      latestId = response.latest_id ?? latestId;
    } catch {
      // polling best-effort
    }
  }

  function headline(entry: Record<string, unknown>): string {
    return String(entry.summary ?? entry.outcome ?? entry.event_type ?? entry.weapon ?? "event");
  }

  function detail(entry: Record<string, unknown>): string {
    return [entry.cause, entry.effect, entry.outcome].filter(Boolean).join(" -> ") || String(entry.description ?? "");
  }
</script>

<Panel title="Combat Log" domain="weapons" priority="secondary" className="combat-log-panel">
  <div class="shell">
    <div class="filters">
      {#each ["all", "railgun", "torpedo", "missile", "pdc"] as item}
        <button class:selected={filter === item} type="button" on:click={() => { filter = item as Filter; entries = []; latestId = 0; void poll(); }}>
          {item.toUpperCase()}
        </button>
      {/each}
    </div>

    <div class="entry-list">
      {#if entries.length === 0}
        <div class="empty">No combat events yet.</div>
      {:else}
        {#each [...entries].reverse() as entry}
          <div class="entry">
            <strong>{headline(entry)}</strong>
            <span>{detail(entry)}</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</Panel>

<style>
  .shell,
  .entry-list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .filters {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
  }

  .filters button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .entry {
    display: grid;
    gap: 4px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border-left: 3px solid rgba(var(--tier-accent-rgb), 0.6);
    background: rgba(255, 255, 255, 0.02);
  }

  .entry span,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
