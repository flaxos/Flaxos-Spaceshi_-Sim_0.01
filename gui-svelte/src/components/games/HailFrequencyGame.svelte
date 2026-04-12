<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedCommsTargetId } from "../../lib/stores/commsUi.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { getCommsContacts, getCommsShip } from "../comms/commsData.js";

  let dial = 500;
  let targetFrequency = 500;
  let signalStrength = 0;
  let locked = false;
  let sentForTarget = "";
  let lockHold = 0;
  let timer: number | null = null;

  $: ship = getCommsShip($gameState);
  $: contacts = getCommsContacts(ship);
  $: activeTarget = contacts.find((contact) => contact.id === $selectedCommsTargetId) ?? contacts[0] ?? null;
  $: if (activeTarget && !$selectedCommsTargetId) selectedCommsTargetId.set(activeTarget.id);
  $: if (activeTarget) {
    const seed = Array.from(activeTarget.id).reduce((sum, char) => sum + char.charCodeAt(0), 0);
    targetFrequency = 80 + (seed % 840);
  }

  onMount(() => {
    timer = window.setInterval(() => {
      const delta = Math.abs(dial - targetFrequency);
      signalStrength = Math.max(0, 1 - delta / 140);
      locked = delta <= 3;
      if (locked) lockHold += 0.1;
      else lockHold = 0;

      if (activeTarget && lockHold >= 1.5 && sentForTarget !== activeTarget.id) {
        sentForTarget = activeTarget.id;
        void wsClient.sendShipCommand("hail_contact", { target: activeTarget.id, frequency: Math.round(dial) });
      }
    }, 100);

    return () => {
      if (timer != null) window.clearInterval(timer);
    };
  });

  $: if (activeTarget && sentForTarget && sentForTarget !== activeTarget.id) {
    sentForTarget = "";
    lockHold = 0;
  }
</script>

<Panel title="Hail Frequency" domain="comms" priority="secondary" className="hail-frequency-game">
  <div class="shell">
    <div class="meta">
      <strong>{activeTarget ? activeTarget.id : "NO TARGET"}</strong>
      <span>{locked ? "LOCKED" : signalStrength > 0.5 ? "SIGNAL DETECTED" : "SCANNING"}</span>
    </div>

    <input type="range" min="0" max="999" step="1" bind:value={dial} />

    <div class="track">
      <div class="noise"></div>
      <div class="signal" style={`width:${(signalStrength * 100).toFixed(1)}%;`}></div>
      <div class="dial" style={`left:${(dial / 999) * 100}%;`}></div>
    </div>

    <div class="readout">
      <span>{Math.round(dial)} MHz</span>
      <span>{Math.round(signalStrength * 100)}% clarity</span>
    </div>
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: 10px;
    padding: var(--space-sm);
  }

  .meta,
  .readout {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .meta span,
  .readout {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .track {
    position: relative;
    height: 48px;
    overflow: hidden;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
  }

  .noise {
    position: absolute;
    inset: 0;
    background:
      repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0 2px, transparent 2px 6px),
      linear-gradient(90deg, rgba(0,0,0,0.2), transparent 40%, rgba(0,0,0,0.25));
  }

  .signal {
    position: absolute;
    inset: 0 auto 0 0;
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.18), rgba(0, 255, 136, 0.55));
  }

  .dial {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 4px;
    transform: translateX(-50%);
    background: var(--status-info);
    box-shadow: 0 0 10px rgba(0, 170, 255, 0.45);
  }
</style>
