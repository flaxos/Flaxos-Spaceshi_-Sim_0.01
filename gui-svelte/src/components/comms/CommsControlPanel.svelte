<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedCommsTargetId } from "../../lib/stores/commsUi.js";
  import {
    emconLevelFromShip,
    getAutoCommsState,
    getCommsContacts,
    getCommsProposals,
    getCommsShip,
    getCommsState,
    getRecentCommsMessages,
    humanMessageTimestamp,
    toStringValue,
  } from "./commsData.js";

  let broadcastText = "";
  let iffCode = "";
  let spoofed = false;
  let emconLevel = 0;
  let feedback = "";

  $: ship = getCommsShip($gameState);
  $: comms = getCommsState(ship);
  $: autoComms = getAutoCommsState(ship);
  $: contacts = getCommsContacts(ship);
  $: proposals = getCommsProposals(ship);
  $: recentMessages = getRecentCommsMessages(ship);
  $: cpuAssistTier = $tier === "cpu-assist";
  $: if (!$selectedCommsTargetId && contacts.length) selectedCommsTargetId.set(contacts[0].id);
  $: if (!iffCode) iffCode = toStringValue(comms.transponder_code, "CIVILIAN");
  $: spoofed = Boolean(comms.is_spoofed);
  $: emconLevel = emconLevel || emconLevelFromShip(ship);

  async function setTransponder(enabled?: boolean) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("set_transponder", {
        enabled: enabled ?? Boolean(comms.transponder_enabled),
        code: iffCode,
        spoofed,
      });
      feedback = "Transponder updated";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Transponder update failed";
    }
  }

  async function hail() {
    if (!$selectedCommsTargetId) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("hail_contact", { target: $selectedCommsTargetId });
      feedback = `Hailing ${$selectedCommsTargetId}`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Hail failed";
    }
  }

  async function broadcast() {
    if (!broadcastText.trim()) return;
    feedback = "";
    try {
      await wsClient.sendShipCommand("broadcast_message", { message: broadcastText.trim() });
      feedback = "Broadcast sent";
      broadcastText = "";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Broadcast failed";
    }
  }

  async function toggleDistress() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("set_distress", { enabled: !Boolean(comms.distress_active) });
      feedback = Boolean(comms.distress_active) ? "Distress beacon cancelled" : "Distress beacon activated";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Distress command failed";
    }
  }

  async function applyEmcon() {
    feedback = "";
    try {
      await wsClient.sendShipCommand("set_emcon", { enabled: emconLevel > 0 });
      feedback = emconLevel > 0 ? `EMCON L${emconLevel}` : "EMCON released";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "EMCON update failed";
    }
  }

  async function toggleAutoComms(enabled: boolean) {
    feedback = "";
    try {
      await wsClient.sendShipCommand(enabled ? "enable_auto_comms" : "disable_auto_comms", {});
      feedback = enabled ? "Auto-comms enabled" : "Auto-comms disabled";
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Auto-comms command failed";
    }
  }

  async function reviewProposal(proposalId: string, approve: boolean) {
    try {
      await wsClient.sendShipCommand(approve ? "approve_comms" : "deny_comms", { proposal_id: proposalId });
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Proposal review failed";
    }
  }
</script>

<Panel title="Comms Control" domain="comms" priority={cpuAssistTier ? "primary" : "secondary"} className="comms-control-panel">
  <div class="shell">
    <section class="status-card">
      <div class="head">
        <span>Status</span>
        <strong>{toStringValue(comms.status, "offline").toUpperCase()}</strong>
      </div>
      <div class="meta">
        <span>Power {Number(comms.radio_power ?? 0).toFixed(0)} W</span>
        <span>Range {Number(comms.radio_range ?? 0).toLocaleString()}</span>
      </div>
    </section>

    {#if cpuAssistTier}
      <section class="proposal-panel">
        <div class="head">
          <span>Auto-Comms</span>
          <strong>{Boolean(autoComms.enabled) ? "ENABLED" : "DISABLED"}</strong>
        </div>
        <div class="toggle-row">
          <button class:active={Boolean(autoComms.enabled)} type="button" on:click={() => toggleAutoComms(true)}>ENABLE</button>
          <button class:active={!Boolean(autoComms.enabled)} type="button" on:click={() => toggleAutoComms(false)}>DISABLE</button>
        </div>
        <div class="policy">Policy {toStringValue(autoComms.policy, "open_comms").replaceAll("_", " ").toUpperCase()}</div>
        {#if proposals.length === 0}
          <div class="empty">No pending comms approvals.</div>
        {:else}
          {#each proposals as proposal}
            <div class="proposal-card">
              <div class="proposal-head">
                <strong>{proposal.action.replaceAll("_", " ").toUpperCase()}</strong>
                <span>{Math.round(proposal.confidence * 100)}%</span>
              </div>
              <div class="proposal-body">{proposal.reason}</div>
              <div class="proposal-actions">
                <button type="button" on:click={() => reviewProposal(proposal.proposalId, true)}>APPROVE</button>
                <button class="secondary" type="button" on:click={() => reviewProposal(proposal.proposalId, false)}>DENY</button>
              </div>
            </div>
          {/each}
        {/if}
      </section>
    {/if}

    <section class="transponder-card">
      <div class="head">
        <span>Transponder</span>
        <strong>{Boolean(comms.transponder_active) ? "ACTIVE" : "QUIET"}</strong>
      </div>
      <div class="toggle-row">
        <button class:active={Boolean(comms.transponder_enabled)} type="button" on:click={() => setTransponder(true)}>ON</button>
        <button class:active={!Boolean(comms.transponder_enabled)} type="button" on:click={() => setTransponder(false)}>OFF</button>
      </div>
      <label class="field">
        <span>IFF / Spoof Code</span>
        <input bind:value={iffCode} maxlength="24" placeholder="CIVILIAN" />
      </label>
      <label class="checkbox">
        <input type="checkbox" bind:checked={spoofed} />
        <span>Broadcast spoofed identity</span>
      </label>
      <button type="button" on:click={() => setTransponder()}>APPLY IDENTITY</button>
    </section>

    <section class="radio-card">
      <div class="head">
        <span>Radio Hail</span>
        <strong>{$selectedCommsTargetId || "NO TARGET"}</strong>
      </div>
      <label class="field">
        <span>Contact</span>
        <select bind:value={$selectedCommsTargetId}>
          <option value="">Select contact</option>
          {#each contacts as contact}
            <option value={contact.id}>{contact.id} · {contact.classification}</option>
          {/each}
        </select>
      </label>
      <button type="button" disabled={!$selectedCommsTargetId} on:click={hail}>HAIL CONTACT</button>
    </section>

    <section class="broadcast-card">
      <div class="head">
        <span>Broadcast</span>
        <strong>{broadcastText.length}/280</strong>
      </div>
      <textarea bind:value={broadcastText} rows="4" maxlength="280" placeholder="All stations, stand by for broadcast..."></textarea>
      <button type="button" disabled={!broadcastText.trim()} on:click={broadcast}>SEND BROADCAST</button>
    </section>

    <section class="emission-card">
      <div class="head">
        <span>Emission Control</span>
        <strong>{emconLevel > 0 ? `L${emconLevel}` : "OPEN"}</strong>
      </div>
      <label class="field">
        <span>EMCON Level</span>
        <select bind:value={emconLevel} on:change={applyEmcon}>
          {#each [0, 1, 2, 3, 4, 5] as level}
            <option value={level}>{level === 0 ? "0 · OPEN" : `${level} · LOW EMISSION`}</option>
          {/each}
        </select>
      </label>
      <button class:alert={Boolean(comms.distress_active)} type="button" on:click={toggleDistress}>
        {Boolean(comms.distress_active) ? "CANCEL DISTRESS" : "ACTIVATE DISTRESS"}
      </button>
    </section>

    <section class="log-card">
      <div class="head">
        <span>Recent Traffic</span>
        <strong>{recentMessages.length}</strong>
      </div>
      {#if recentMessages.length === 0}
        <div class="empty">No recent radio traffic.</div>
      {:else}
        <div class="log-list">
          {#each recentMessages.slice().reverse() as message}
            <div class="log-row">
              <span>{humanMessageTimestamp(Number(message.time ?? message.timestamp ?? 0))}</span>
              <strong>{toStringValue(message.from, "SYS")}</strong>
              <span>{toStringValue(message.message, "--")}</span>
            </div>
          {/each}
        </div>
      {/if}
    </section>

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

  .status-card,
  .proposal-panel,
  .transponder-card,
  .radio-card,
  .broadcast-card,
  .emission-card,
  .log-card,
  .feedback {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .head,
  .meta,
  .proposal-head,
  .proposal-actions,
  .toggle-row,
  .log-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .field {
    display: grid;
    gap: 6px;
  }

  .field span,
  .meta,
  .policy,
  .proposal-body,
  .log-row,
  .empty,
  .feedback,
  .checkbox span {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .checkbox {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  input,
  select,
  textarea,
  button {
    width: 100%;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  textarea {
    resize: vertical;
  }

  .toggle-row button {
    flex: 1;
  }

  button.active {
    border-color: rgba(0, 255, 136, 0.4);
    background: rgba(0, 255, 136, 0.08);
  }

  button.secondary {
    color: var(--text-secondary);
  }

  button.alert {
    border-color: rgba(255, 68, 68, 0.4);
    background: rgba(255, 68, 68, 0.12);
  }

  .log-list {
    display: grid;
    gap: 6px;
    max-height: 180px;
    overflow: auto;
  }

  .log-row {
    display: grid;
    grid-template-columns: 56px 56px 1fr;
    align-items: start;
    gap: 8px;
    text-transform: none;
    letter-spacing: normal;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
