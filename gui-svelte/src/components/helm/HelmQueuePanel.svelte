<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, extractShipState, formatDuration, getQueueState, toNumber, toStringValue } from "./helmData.js";

  interface QueueEntry {
    id: number | null;
    command: string;
    status: string;
    elapsed: number;
    target: string;
  }

  let polledQueue: { active: QueueEntry | null; pending: QueueEntry[] } = { active: null, pending: [] };
  let feedback = "";
  let pollHandle: number | null = null;

  $: ship = extractShipState($gameState);
  $: storeQueue = getQueueState(ship);
  $: queue = polledQueue.active || polledQueue.pending.length ? polledQueue : storeQueue;

  onMount(() => {
    void refreshQueue();
    pollHandle = window.setInterval(() => void refreshQueue(), 2000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  function parseEntry(value: unknown): QueueEntry | null {
    const entry = asRecord(value);
    if (!entry) return null;
    return {
      id: entry.id == null ? null : toNumber(entry.id),
      command: toStringValue(entry.command, "unknown"),
      status: toStringValue(entry.status, "pending"),
      elapsed: toNumber(entry.elapsed),
      target: toStringValue(entry.target),
    };
  }

  async function refreshQueue() {
    try {
      const response = await wsClient.sendShipCommand("helm_queue_status", {});
      const record = asRecord(response);
      const queueState = asRecord(record?.queue) ?? record;
      polledQueue = {
        active: parseEntry(queueState?.active),
        pending: Array.isArray(queueState?.pending) ? queueState.pending.map(parseEntry).filter((entry): entry is QueueEntry => Boolean(entry)) : [],
      };
    } catch {
      polledQueue = { active: null, pending: [] };
    }
  }

  async function clearQueue() {
    await wsClient.sendShipCommand("clear_helm_queue", {});
    feedback = "Queue cleared";
    await refreshQueue();
  }

  async function interruptQueue() {
    await wsClient.sendShipCommand("interrupt_helm_queue", {});
    feedback = "Active command interrupted";
    await refreshQueue();
  }
</script>

<Panel title="Helm Queue" domain="helm" priority="secondary" className="helm-queue-panel">
  <div class="shell">
    <div class="actions">
      <button on:click={interruptQueue} disabled={!queue.active}>Interrupt Current</button>
      <button on:click={clearQueue} disabled={!queue.active && queue.pending.length === 0}>Clear Queue</button>
    </div>

    {#if queue.active}
      <div class="active-card">
        <div class="eyebrow">Active</div>
        <strong>{queue.active.command.toUpperCase()}</strong>
        <span>{queue.active.target || "ship-local"}</span>
        <span>Elapsed {formatDuration(queue.active.elapsed)}</span>
      </div>
    {/if}

    <div class="pending-shell">
      <div class="eyebrow">Pending</div>
      {#if queue.pending.length === 0}
        <div class="empty">No queued helm commands.</div>
      {:else}
        {#each queue.pending as entry}
          <div class="pending-row">
            <strong>{entry.command}</strong>
            <span>{entry.target || "ship-local"}</span>
            <span>{entry.status}</span>
          </div>
        {/each}
      {/if}
    </div>

    {#if feedback}
      <div class="feedback">{feedback}</div>
    {/if}
  </div>
</Panel>

<style>
  .shell,
  .pending-shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-xs);
  }

  .active-card,
  .pending-row {
    display: grid;
    gap: 4px;
    padding: 10px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: rgba(var(--tier-accent-rgb), 0.08);
  }

  .pending-row {
    background: rgba(255, 255, 255, 0.02);
  }

  .eyebrow,
  .empty,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
