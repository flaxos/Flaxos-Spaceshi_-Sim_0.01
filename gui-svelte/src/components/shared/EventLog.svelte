<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, toStringValue } from "../helm/helmData.js";

  export let filter: string[] = [];
  export let title = "Event Log";
  export let priority: "primary" | "secondary" | "tertiary" = "secondary";
  export let domain: "nav" | "sensor" | "weapons" | "power" | "comms" | "helm" | "" = "";

  interface EventEntry {
    type: string;
    timestamp: number;
    simTime: number;
    shipId: string;
    message: string;
  }

  let entries: EventEntry[] = [];
  let pollHandle: number | null = null;

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 1200);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  function matches(type: string): boolean {
    if (filter.length === 0) return true;
    const lower = type.toLowerCase();
    return filter.some((needle) => lower.includes(needle.toLowerCase()));
  }

  function formatEntry(raw: unknown): EventEntry | null {
    const event = asRecord(raw);
    if (!event) return null;
    const payload = asRecord(event.data) ?? {};
    const type = toStringValue(event.type, "event");
    if (!matches(type)) return null;

    return {
      type,
      timestamp: typeof event.timestamp === "number" ? event.timestamp : Date.now() / 1000,
      simTime: typeof event.t === "number" ? event.t : 0,
      shipId: toStringValue(event.ship_id),
      message:
        toStringValue(payload.message)
        || toStringValue(payload.status)
        || [payload.subsystem, payload.system, payload.target, payload.reactor].filter(Boolean).join(" ")
        || type.replaceAll("_", " "),
    };
  }

  async function refresh() {
    try {
      const response = await wsClient.send("get_events", { limit: 160 });
      const record = asRecord(response);
      const source = Array.isArray(record?.events) ? record.events : [];
      entries = source
        .map(formatEntry)
        .filter((entry): entry is EventEntry => Boolean(entry))
        .slice(-120)
        .reverse();
    } catch {
      // best effort polling
    }
  }

  function clock(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }
</script>

<Panel {title} {priority} {domain} className="shared-event-log-panel">
  <div class="shell">
    {#if entries.length === 0}
      <div class="empty">No matching events.</div>
    {:else}
      {#each entries as entry}
        <div class="entry">
          <div class="meta">
            <span class="time">{clock(entry.timestamp)}</span>
            <span class="type">{entry.type.replaceAll("_", " ").toUpperCase()}</span>
          </div>
          <div class="message">{entry.message}</div>
        </div>
      {/each}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-xs);
    padding: var(--space-sm);
    max-height: 100%;
  }

  .entry {
    display: grid;
    gap: 4px;
    padding: 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .meta {
    display: flex;
    gap: var(--space-sm);
    justify-content: space-between;
    align-items: center;
  }

  .time,
  .type,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .time,
  .type {
    font-family: var(--font-mono);
  }

  .message {
    color: var(--text-primary);
    font-size: 0.8rem;
  }
</style>
