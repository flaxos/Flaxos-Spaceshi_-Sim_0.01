<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { humanMessageTimestamp, normalizeStationMessages, type StationMessageRow } from "./commsData.js";

  const STATION_OPTIONS = ["all", "helm", "tactical", "ops", "engineering", "science", "comms", "captain", "fleet_commander"];
  const STATION_COLORS: Record<string, string> = {
    all: "var(--status-info)",
    helm: "#50a6ff",
    tactical: "#ff6666",
    ops: "#6be0a8",
    engineering: "#ffb26a",
    science: "#69d7ff",
    comms: "#d29dff",
    captain: "#ffd66b",
    fleet_commander: "#ff8ece",
  };

  let messages: StationMessageRow[] = [];
  let draft = "";
  let target = "all";
  let latestId = 0;
  let pollHandle: number | null = null;

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 1000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.send("get_station_messages", { since_id: latestId });
      const incoming = normalizeStationMessages(response);
      if (!incoming.length) return;
      messages = [...messages, ...incoming].slice(-120);
      latestId = messages[messages.length - 1]?.id ?? latestId;
    } catch {
      // best effort
    }
  }

  async function sendMessage() {
    if (!draft.trim()) return;
    try {
      await wsClient.send("station_message", { to: target, text: draft.trim() });
      draft = "";
      await refresh();
    } catch {
      // best effort
    }
  }
</script>

<Panel title="Station Chat" domain="comms" priority="secondary" className="station-chat-panel">
  <div class="shell">
    <div class="messages">
      {#if messages.length === 0}
        <div class="empty">No station messages yet.</div>
      {:else}
        {#each messages as message}
          <div class="message-row">
            <span class="time">{humanMessageTimestamp(message.timestamp)}</span>
            <span class="badge" style={`--badge-color:${STATION_COLORS[message.fromStation] ?? "#888899"};`}>
              {message.fromStation.toUpperCase()}
            </span>
            <div class="text">
              {#if message.to !== "all"}
                <strong>{message.to.toUpperCase()}</strong>
              {/if}
              {message.text}
            </div>
          </div>
        {/each}
      {/if}
    </div>

    <div class="composer">
      <select bind:value={target}>
        {#each STATION_OPTIONS as option}
          <option value={option}>{option.toUpperCase()}</option>
        {/each}
      </select>
      <input
        bind:value={draft}
        maxlength="500"
        placeholder="Coordinate with your crew"
        on:keydown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void sendMessage();
          }
        }}
      />
      <button type="button" disabled={!draft.trim()} on:click={sendMessage}>SEND</button>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
    min-height: 0;
  }

  .messages {
    display: grid;
    gap: 6px;
    max-height: 320px;
    overflow: auto;
  }

  .message-row {
    display: grid;
    grid-template-columns: 54px 118px 1fr;
    gap: 8px;
    align-items: start;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .time,
  .empty,
  .text,
  .composer select,
  .composer input,
  .composer button {
    font-size: var(--font-size-xs);
  }

  .time,
  .empty,
  .text {
    color: var(--text-secondary);
  }

  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 24px;
    padding: 0 8px;
    border-radius: 999px;
    border: 1px solid color-mix(in srgb, var(--badge-color) 50%, transparent);
    color: var(--badge-color);
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.08em;
  }

  .text strong {
    margin-right: 6px;
    color: var(--text-primary);
    font-family: var(--font-mono);
  }

  .composer {
    display: grid;
    grid-template-columns: 110px 1fr 90px;
    gap: 8px;
  }

  .composer select,
  .composer input,
  .composer button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
  }

  @media (max-width: 640px) {
    .message-row {
      grid-template-columns: 1fr;
    }

    .composer {
      grid-template-columns: 1fr;
    }
  }
</style>
