<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    extractShipState,
    formatBearing,
    formatContactSummary,
    formatContactVector,
    getLockedTargetId,
    getSensorState,
    getTacticalContacts,
    toNumber,
  } from "./tacticalData.js";
  import { lockTarget } from "./tacticalActions.js";

  export let passive = false;

  let busy = false;

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: sensors = getSensorState(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";
  $: manualTier = $tier === "manual";
  $: cooldown = toNumber(sensors.ping_cooldown_remaining);
  $: canPing = !passive && Boolean(sensors.can_ping ?? true) && cooldown <= 0;

  async function pingSensors() {
    if (!canPing) return;
    busy = true;
    try {
      await wsClient.sendShipCommand("ping_sensors", {});
    } finally {
      busy = false;
    }
  }

  async function lockContact(contactId: string) {
    selectedTacticalTargetId.set(contactId);
    if (passive) return;
    await lockTarget(contactId);
  }
</script>

<Panel title={passive ? "Passive Contacts" : "Sensor Contacts"} domain="sensor" priority={$tier === "manual" ? "primary" : "secondary"} className="sensor-contacts-panel">
  <div class="shell">
    {#if !passive}
      <div class="toolbar">
        <button
          disabled={!canPing || busy}
          title={cooldown > 0 ? `Active ping cooling down — ready in ${cooldown.toFixed(1)}s` : busy ? "Pinging…" : "Send active sonar ping to resolve contacts"}
          on:click={pingSensors}
        >
          {cooldown > 0 ? `PING ${cooldown.toFixed(1)}s` : busy ? "PINGING…" : "PING SENSORS"}
        </button>
        <div class="summary">{contacts.length} contacts</div>
      </div>
    {:else}
      <div class="toolbar passive-bar">
        <span class="passive-badge">PASSIVE</span>
        <div class="summary">{contacts.length} contacts · read-only</div>
      </div>
    {/if}

    <div class="list">
      {#if contacts.length === 0}
        <div class="empty">No contacts resolved.</div>
      {:else}
        {#each contacts as contact}
          <button
            class="contact-row"
            class:selected={contact.id === $selectedTacticalTargetId || contact.id === lockedTargetId}
            class:passive={passive}
            type="button"
            disabled={passive}
            title={passive ? "Passive mode — active lock unavailable" : `Lock ${contact.id} as tactical target`}
            on:click={() => lockContact(contact.id)}
          >
            <div class="topline">
              <strong>{contact.id}</strong>
              <span class="threat {contact.threatLevel}">{contact.threatLevel.toUpperCase()}</span>
            </div>

            {#if cpuAssistTier}
              <div class="primary-line">{contact.classification || "Unknown"} · {Math.round(contact.threatScore * 100)} threat</div>
            {:else}
              <div class="primary-line">{contact.classification || "Unknown"} · {formatContactSummary(contact)}</div>
            {/if}

            {#if !arcadeTier && !cpuAssistTier}
              <div class="detail-line">
                <span>Bearing {formatBearing(contact.bearing)}</span>
                <span>Closure {contact.closureRate >= 0 ? "+" : ""}{contact.closureRate.toFixed(0)} m/s</span>
              </div>
            {/if}

            {#if manualTier}
              <div class="detail-line">
                <span>Signal {contact.signalStrength.toFixed(2)}</span>
                <span>V {formatContactVector(contact)}</span>
              </div>
            {/if}

            <div class="confidence-track" aria-label="Contact confidence">
              <div class="confidence-fill {contact.threatLevel}" style={`width: ${(contact.confidence * 100).toFixed(0)}%;`}></div>
            </div>
          </button>
        {/each}
      {/if}
    </div>
  </div>
</Panel>

<style>
  .shell,
  .list {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .toolbar,
  .topline,
  .detail-line {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .summary,
  .primary-line,
  .detail-line,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .contact-row {
    display: grid;
    gap: 6px;
    width: 100%;
    text-align: left;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.02);
  }

  .contact-row.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .contact-row.passive {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .passive-bar {
    align-items: center;
  }

  .passive-badge {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    padding: 3px 7px;
    border-radius: 3px;
    background: rgba(255, 216, 77, 0.18);
    color: #ffd84d;
    border: 1px solid rgba(255, 216, 77, 0.35);
  }

  .contact-row strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .threat {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.08em;
  }

  .threat.green,
  .confidence-fill.green {
    color: var(--status-nominal);
    background: rgba(0, 255, 136, 0.85);
  }

  .threat.yellow,
  .confidence-fill.yellow {
    color: #ffd84d;
    background: rgba(255, 216, 77, 0.85);
  }

  .threat.orange,
  .confidence-fill.orange {
    color: #ff9d47;
    background: rgba(255, 157, 71, 0.9);
  }

  .threat.red,
  .confidence-fill.red {
    color: var(--status-critical);
    background: rgba(255, 68, 68, 0.9);
  }

  .confidence-track {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .confidence-fill {
    height: 100%;
  }
</style>
