<script lang="ts">
  /**
   * CombatLog — prototype-aligned event log.
   *
   * Each entry is a single row with:
   *   - timestamp (mono, dim)
   *   - color-coded type badge (HIT/MISS/FIRE/LOCK/ALRT/DET/SYS)
   *   - message text
   *   - left border tinted to match type
   * Newest at top; latest row plays a slideUp animation on arrival.
   * Server-side: polls `get_combat_log` every 900ms using `since_id` + optional `weapon` filter.
   */
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  type Filter = "all" | "railgun" | "torpedo" | "missile" | "pdc";

  type LogType = "hit" | "miss" | "fire" | "lock" | "alert" | "detect" | "system";
  interface DisplayEntry {
    key: string;
    type: LogType;
    timestamp: string;
    message: string;
  }

  let filter: Filter = "all";
  let entries: DisplayEntry[] = [];
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
      const response = await wsClient.send("get_combat_log", params) as {
        entries?: Array<Record<string, unknown>>;
        latest_id?: number;
      };
      if (Array.isArray(response.entries) && response.entries.length > 0) {
        const mapped = response.entries.map(normalize);
        entries = [...entries, ...mapped].slice(-200);
      }
      latestId = response.latest_id ?? latestId;
    } catch {
      // polling best-effort
    }
  }

  function setFilter(next: Filter) {
    filter = next;
    entries = [];
    latestId = 0;
    void poll();
  }

  function normalize(entry: Record<string, unknown>): DisplayEntry {
    const id = String(entry.id ?? entry.event_id ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
    return {
      key: id,
      type: classifyType(entry),
      timestamp: extractTimestamp(entry),
      message: buildMessage(entry),
    };
  }

  function classifyType(entry: Record<string, unknown>): LogType {
    const explicit = String(entry.type ?? entry.event_type ?? "").toLowerCase();
    if (explicit.includes("hit") || explicit === "impact") return "hit";
    if (explicit.includes("miss")) return "miss";
    if (explicit.includes("fire") || explicit.includes("launch") || explicit.includes("shot")) return "fire";
    if (explicit.includes("lock") || explicit.includes("acquire")) return "lock";
    if (explicit.includes("alert") || explicit.includes("warn")) return "alert";
    if (explicit.includes("detect") || explicit.includes("scan") || explicit.includes("ping")) return "detect";
    if (explicit.includes("system") || explicit.includes("damage") || explicit.includes("subsys")) return "system";

    const outcome = String(entry.outcome ?? "").toLowerCase();
    if (outcome.includes("hit")) return "hit";
    if (outcome.includes("miss")) return "miss";

    return "system";
  }

  function extractTimestamp(entry: Record<string, unknown>): string {
    const raw = entry.timestamp ?? entry.time ?? entry.t ?? entry.mission_time;
    if (typeof raw === "string" && raw.length > 0) return raw.slice(-8);
    if (typeof raw === "number" && Number.isFinite(raw)) {
      const total = Math.floor(raw);
      const h = String(Math.floor(total / 3600)).padStart(2, "0");
      const m = String(Math.floor((total / 60) % 60)).padStart(2, "0");
      const s = String(total % 60).padStart(2, "0");
      return `${h}:${m}:${s}`;
    }
    const now = new Date();
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
  }

  function buildMessage(entry: Record<string, unknown>): string {
    const primary = entry.summary ?? entry.message ?? entry.description;
    if (typeof primary === "string" && primary.length > 0) return primary;
    const parts = [entry.weapon, entry.cause, entry.effect, entry.outcome]
      .filter((v) => typeof v === "string" && v)
      .map((v) => String(v));
    return parts.length > 0 ? parts.join(" · ") : String(entry.event_type ?? "event");
  }

  function typeColor(t: LogType): string {
    switch (t) {
      case "hit":    return "var(--nom)";
      case "miss":   return "var(--warn)";
      case "fire":   return "#ff8080";
      case "lock":   return "var(--info)";
      case "alert":  return "var(--warn)";
      case "detect": return "var(--info)";
      case "system": return "var(--crit)";
    }
  }

  function typeBg(t: LogType): string {
    const col = typeColor(t);
    // 0x18 alpha ≈ 9.4% opacity badge background
    if (col === "var(--nom)")  return "rgba(0, 221, 106, 0.09)";
    if (col === "var(--warn)") return "rgba(239, 160, 32, 0.09)";
    if (col === "var(--info)") return "rgba(30, 140, 255, 0.09)";
    if (col === "var(--crit)") return "rgba(232, 48, 48, 0.09)";
    return "rgba(255, 128, 128, 0.09)";
  }

  function typeTag(t: LogType): string {
    return ({
      hit: "HIT",
      miss: "MISS",
      fire: "FIRE",
      lock: "LOCK",
      alert: "ALRT",
      detect: "DET",
      system: "SYS",
    } as const)[t];
  }

  $: reversed = [...entries].reverse();
</script>

<Panel title="Combat Log" domain="weapons" priority="secondary" className="combat-log-panel">
  <div class="shell">
    <!-- Filter chips -->
    <div class="filters">
      {#each ["all", "railgun", "torpedo", "missile", "pdc"] as item}
        <button
          type="button"
          class="chip"
          class:selected={filter === item}
          on:click={() => setFilter(item as Filter)}
        >{item.toUpperCase()}</button>
      {/each}
    </div>

    <!-- Entry list -->
    <div class="list">
      {#if reversed.length === 0}
        <div class="empty">No combat events yet.</div>
      {:else}
        {#each reversed as entry, i (entry.key)}
          {@const col = typeColor(entry.type)}
          {@const bg = typeBg(entry.type)}
          <div
            class="entry"
            class:newest={i === 0}
            style="border-left-color: {col};"
          >
            <span class="ts">{entry.timestamp}</span>
            <span class="type-badge" style="color: {col}; background: {bg};">
              {typeTag(entry.type)}
            </span>
            <span class="msg">{entry.message}</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .filters {
    display: flex;
    gap: 4px;
    padding: 5px 8px;
    border-bottom: 1px solid var(--bd-subtle);
    flex-shrink: 0;
  }

  .chip {
    flex: 1;
    background: transparent;
    border: 1px solid var(--bd-subtle);
    color: var(--tx-dim);
    padding: 3px 6px;
    border-radius: 2px;
    font-family: var(--font-mono);
    font-size: 0.52rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: border-color 0.12s, color 0.12s, background 0.12s;
  }

  .chip:hover {
    color: var(--tx-sec);
    border-color: var(--bd-default);
  }

  .chip.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.1);
    color: var(--tx-bright);
  }

  .list {
    flex: 1;
    overflow-y: auto;
    font-family: var(--font-mono);
  }

  .entry {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    padding: 5px 10px;
    border-bottom: 1px solid var(--bd-subtle);
    border-left: 3px solid;
  }

  .entry.newest {
    animation: slideUp 0.18s ease-out;
  }

  .ts {
    font-size: 0.56rem;
    color: var(--tx-dim);
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 1px;
    font-variant-numeric: tabular-nums;
  }

  .type-badge {
    font-size: 0.56rem;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
    padding: 1px 4px;
    border-radius: 1px;
    letter-spacing: 0.04em;
    align-self: flex-start;
  }

  .msg {
    font-size: 0.63rem;
    color: var(--tx-primary);
    line-height: 1.35;
    word-break: break-word;
  }

  .empty {
    padding: 16px 10px;
    text-align: center;
    font-size: var(--font-size-xs);
    color: var(--tx-dim);
  }
</style>
