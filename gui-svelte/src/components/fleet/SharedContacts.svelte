<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { localSharedContacts, formatDistance, getFleetShip } from "./fleetData.js";

  let shared = new Set<string>();
  let hostile = new Set<string>();
  let feedback = "";

  $: ship = getFleetShip($gameState);
  $: contacts = localSharedContacts(ship);

  async function share(contactId: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("share_contact", {
        contact: contactId,
        hostile: hostile.has(contactId),
      });
      shared = new Set([...shared, contactId]);
      feedback = `${contactId} shared with fleet`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Share failed";
    }
  }

  function toggleHostile(contactId: string) {
    const next = new Set(hostile);
    if (next.has(contactId)) next.delete(contactId);
    else next.add(contactId);
    hostile = next;
  }
</script>

<Panel title="Shared Contacts" domain="weapons" priority="secondary" className="shared-contacts-panel">
  <div class="shell">
    {#if contacts.length === 0}
      <div class="empty">No contacts available for data-link sharing.</div>
    {:else}
      {#each contacts as contact}
        <div class="contact-row">
          <div class="info">
            <strong>{contact.id}</strong>
            <span>{contact.classification} · {contact.sourceShip} · {formatDistance(contact.distance)}</span>
          </div>
          <div class="actions">
            <label class="hostile-toggle">
              <input type="checkbox" checked={hostile.has(contact.id)} on:change={() => toggleHostile(contact.id)} />
              <span>HOSTILE</span>
            </label>
            <button type="button" class:active={shared.has(contact.id)} on:click={() => share(contact.id)}>
              {shared.has(contact.id) ? "RESHARE" : "SHARE"}
            </button>
          </div>
        </div>
      {/each}
    {/if}

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

  .contact-row,
  .feedback,
  .empty {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .info,
  .actions {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .info span,
  .hostile-toggle span,
  .feedback,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .hostile-toggle {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  button {
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }

  button.active {
    border-color: rgba(var(--tier-accent-rgb), 0.4);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .feedback {
    color: var(--status-info);
  }
</style>
