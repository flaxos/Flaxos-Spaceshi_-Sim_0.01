<script lang="ts">
  /**
   * SensorContacts — prototype-aligned contact list.
   *
   * Layout columns: IFF tag | contact ID+name | distance | bearing.
   * Color-coded by IFF (hostile red, friendly green, unknown orange).
   * Threat badge on high-threat contacts. Pulsing animation for ordnance.
   * Clicking a contact selects it as the tactical target.
   */
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    getLockedTargetId,
    getSensorState,
    getTacticalContacts,
    toNumber,
    type TacticalContact,
  } from "./tacticalData.js";
  import { lockTarget } from "./tacticalActions.js";

  export let passive = false;

  let busy = false;

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: sensors = getSensorState(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: cooldown = toNumber(sensors.ping_cooldown_remaining);
  $: canPing = !passive && Boolean(sensors.can_ping ?? true) && cooldown <= 0;

  // Sort: ordnance first (threats!), then by distance
  $: sortedContacts = [...contacts].sort((a, b) => {
    const aOrd = isOrdnance(a) ? 0 : 1;
    const bOrd = isOrdnance(b) ? 0 : 1;
    if (aOrd !== bOrd) return aOrd - bOrd;
    return a.distance - b.distance;
  });

  $: hostileCount = contacts.filter((c) => iffKind(c) === "hostile").length;

  function iffKind(c: TacticalContact): "hostile" | "friendly" | "unknown" | "neutral" {
    const dip = c.diplomaticState.toLowerCase();
    if (dip.includes("hostile") || c.threatLevel === "red" || c.threatLevel === "orange") return "hostile";
    if (dip.includes("friend") || dip.includes("allied")) return "friendly";
    if (dip.includes("unknown") || dip === "") return "unknown";
    return "neutral";
  }

  function iffTag(c: TacticalContact): string {
    const k = iffKind(c);
    if (k === "hostile") return "HOT";
    if (k === "friendly") return "FRD";
    if (k === "unknown") return "UNK";
    return "NEU";
  }

  function iffColor(c: TacticalContact): string {
    const k = iffKind(c);
    if (k === "hostile") return "#e83030";
    if (k === "friendly") return "#00dd6a";
    if (k === "unknown") return "#efa020";
    return "#6888aa";
  }

  function isOrdnance(c: TacticalContact): boolean {
    return /torpedo|missile|ordnance/i.test(c.classification);
  }

  function threatBadge(c: TacticalContact): string | null {
    if (isOrdnance(c)) return "CRIT";
    if (c.threatLevel === "red") return "HIGH";
    if (c.threatLevel === "orange") return "MED";
    return null;
  }

  function threatColor(label: string): string {
    if (label === "CRIT" || label === "HIGH") return "#e83030";
    if (label === "MED") return "#efa020";
    return "#3a3a52";
  }

  function distStr(m: number): string {
    if (m >= 1000) return `${(m / 1000).toFixed(0)}k`;
    return `${Math.round(m)}m`;
  }

  async function pingSensors() {
    if (!canPing) return;
    busy = true;
    try {
      await wsClient.sendShipCommand("ping_sensors", {});
    } finally {
      busy = false;
    }
  }

  async function selectContact(contactId: string) {
    selectedTacticalTargetId.set(contactId);
    if (passive) return;
    await lockTarget(contactId);
  }
</script>

<Panel
  title={passive ? "Passive Contacts" : "Sensor Contacts"}
  domain="sensor"
  priority="primary"
  className="sensor-contacts-panel"
>
  <div class="shell">
    <!-- Toolbar -->
    {#if !passive}
      <div class="toolbar">
        <button
          class="ping-btn"
          disabled={!canPing || busy}
          title={cooldown > 0
            ? `Active ping cooling down — ready in ${cooldown.toFixed(1)}s`
            : busy ? "Pinging…" : "Send active sensor ping to resolve contacts"}
          on:click={pingSensors}
        >
          {cooldown > 0 ? `PING ${cooldown.toFixed(1)}s` : busy ? "PINGING…" : "PING"}
        </button>
        <span class="status-badge" class:hot={hostileCount > 0}>
          {hostileCount > 0 ? `${hostileCount} HOT` : `${contacts.length} LIVE`}
        </span>
      </div>
    {:else}
      <div class="toolbar passive-bar">
        <span class="passive-badge">PASSIVE</span>
        <span class="status-badge">{contacts.length} RO</span>
      </div>
    {/if}

    <!-- Column headers -->
    <div class="header">
      <span>IFF</span>
      <span>Contact</span>
      <span class="right">Dist</span>
      <span class="right">Brg</span>
    </div>

    <!-- List -->
    <div class="list">
      {#if sortedContacts.length === 0}
        <div class="empty">No contacts resolved.</div>
      {:else}
        {#each sortedContacts as c (c.id)}
          {@const kind = iffKind(c)}
          {@const col = iffColor(c)}
          {@const tag = iffTag(c)}
          {@const badge = threatBadge(c)}
          {@const ord = isOrdnance(c)}
          {@const selected = c.id === $selectedTacticalTargetId || c.id === lockedTargetId}
          <button
            class="row"
            class:selected
            class:torpedo={ord}
            class:passive
            type="button"
            disabled={passive}
            title={passive ? "Passive — cannot designate" : `Designate ${c.id}`}
            style="--iff: {col}; --iff-border: {col}50;"
            on:click={() => selectContact(c.id)}
          >
            <span class="iff" style="color: {col};">{tag}</span>
            <div class="ident">
              <div class="ident-top">
                <strong class="cid">{c.id}</strong>
                {#if badge}
                  <span class="threat" style="color: {threatColor(badge)}; border-color: {threatColor(badge)}44;">{badge}</span>
                {/if}
              </div>
              <div class="cname">
                {(c.name.length > 16 ? c.name.slice(0, 15) + "…" : c.name).toUpperCase()}
              </div>
            </div>
            <span class="num">{distStr(c.distance)}</span>
            <span class="num">{String(Math.round(c.bearing < 0 ? c.bearing + 360 : c.bearing)).padStart(3, "0")}°</span>
          </button>
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

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    border-bottom: 1px solid var(--bd-subtle);
    background: rgba(0, 0, 0, 0.18);
    gap: 6px;
    flex-shrink: 0;
  }

  .ping-btn {
    background: transparent;
    border: 1px solid var(--bd-default);
    color: var(--tx-sec);
    padding: 3px 8px;
    border-radius: 2px;
    font-family: var(--font-mono);
    font-size: 0.59rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
  }

  .ping-btn:hover:not(:disabled) {
    color: var(--tx-bright);
    border-color: var(--bd-focus);
  }

  .status-badge {
    font-size: 0.51rem;
    font-weight: 700;
    font-family: var(--font-mono);
    padding: 1px 5px;
    border-radius: 2px;
    color: var(--nom);
    background: rgba(0, 221, 106, 0.1);
    border: 1px solid rgba(0, 221, 106, 0.28);
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }

  .status-badge.hot {
    color: var(--crit);
    background: rgba(232, 48, 48, 0.1);
    border-color: rgba(232, 48, 48, 0.4);
  }

  .passive-badge {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    padding: 2px 6px;
    border-radius: 2px;
    background: rgba(255, 216, 77, 0.18);
    color: #ffd84d;
    border: 1px solid rgba(255, 216, 77, 0.35);
  }

  .header {
    display: grid;
    grid-template-columns: 34px 1fr 48px 52px;
    padding: 3px 8px;
    border-bottom: 1px solid var(--bd-subtle);
    font-size: 0.52rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    flex-shrink: 0;
  }

  .header .right {
    text-align: right;
  }

  .list {
    flex: 1;
    overflow-y: auto;
  }

  .row {
    display: grid;
    grid-template-columns: 34px 1fr 48px 52px;
    padding: 5px 8px;
    border: none;
    border-bottom: 1px solid var(--bd-subtle);
    border-left: 3px solid var(--iff-border, var(--bd-default));
    border-radius: 0;
    background: transparent;
    text-align: left;
    cursor: pointer;
    font-family: inherit;
    width: 100%;
    transition: background 0.1s ease;
  }

  .row:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.03);
  }

  .row.selected {
    background: rgba(255, 255, 255, 0.04);
    border-left-color: #fff;
  }

  .row.torpedo {
    background: rgba(232, 48, 48, 0.06);
    animation: pulse 1s ease-in-out infinite;
  }

  .row.passive {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .iff {
    font-size: 0.57rem;
    font-family: var(--font-mono);
    font-weight: 700;
    letter-spacing: 0.04em;
    align-self: center;
  }

  .ident {
    display: flex;
    flex-direction: column;
    gap: 1px;
    overflow: hidden;
    min-width: 0;
  }

  .ident-top {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .cid {
    font-size: 0.68rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--tx-primary);
  }

  .row.selected .cid {
    color: var(--tx-bright);
  }

  .threat {
    font-size: 0.48rem;
    font-family: var(--font-mono);
    padding: 0 3px;
    border-radius: 1px;
    border: 1px solid;
    letter-spacing: 0.04em;
  }

  .cname {
    font-size: 0.58rem;
    color: var(--tx-dim);
    font-family: var(--font-mono);
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
  }

  .num {
    font-size: 0.63rem;
    font-family: var(--font-mono);
    text-align: right;
    color: var(--tx-primary);
    font-variant-numeric: tabular-nums;
    align-self: center;
  }

  .empty {
    padding: 14px;
    text-align: center;
    font-size: var(--font-size-xs);
    color: var(--tx-dim);
  }
</style>
