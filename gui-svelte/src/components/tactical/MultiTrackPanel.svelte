<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getMultiTrackState, getPdcMounts, getTacticalContacts, getWeaponMounts, toStringValue } from "./tacticalData.js";

  let assignWeapon = "";

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: multiTrack = getMultiTrackState(ship);
  $: pdcMounts = getPdcMounts(ship);
  $: weaponMounts = getWeaponMounts(ship);

  async function addTrack() {
    if (!$selectedTacticalTargetId) return;
    await wsClient.sendShipCommand("add_track", { contact_id: $selectedTacticalTargetId });
  }

  async function removeTrack(contactId: string) {
    await wsClient.sendShipCommand("remove_track", { contact_id: contactId });
  }

  async function assignPdc(contactId: string, mountId: string) {
    if (!mountId) return;
    await wsClient.sendShipCommand("assign_pdc_target", { mount_id: mountId, contact_id: contactId });
  }

  async function splitFire(contactId: string, mountId: string) {
    if (!mountId) return;
    await wsClient.sendShipCommand("split_fire", { mount_id: mountId, contact_id: contactId });
  }

  async function clearAssignments() {
    await wsClient.sendShipCommand("clear_assignments", {});
  }
</script>

<Panel title="Multi-Track" domain="weapons" priority="secondary" className="multi-track-panel">
  <div class="shell">
    <div class="toolbar">
      <button disabled={!$selectedTacticalTargetId} on:click={addTrack}>ADD TRACK</button>
      <button disabled={multiTrack.trackCount === 0} on:click={clearAssignments}>CLEAR ASSIGNMENTS</button>
    </div>

    {#if multiTrack.trackCount === 0}
      <div class="empty">No multi-target tracks assigned.</div>
    {:else}
      {#each multiTrack.tracks as track}
        <div class="track-card">
          <div class="header">
            <strong>{toStringValue(track.contact_id)}</strong>
            <span>Priority {track.priority ?? 0} · Q {Math.round(Number(track.quality_modifier ?? 0) * 100)}%</span>
          </div>
          <div class="assignments">
            <label>
              <span>PDC</span>
              <select on:change={(event) => assignPdc(String(track.contact_id), (event.currentTarget as HTMLSelectElement).value)}>
                <option value="">Assign</option>
                {#each pdcMounts as mount}
                  <option value={mount.id}>{mount.id}</option>
                {/each}
              </select>
            </label>
            <label>
              <span>Weapon</span>
              <select bind:value={assignWeapon} on:change={(event) => splitFire(String(track.contact_id), (event.currentTarget as HTMLSelectElement).value)}>
                <option value="">Split-fire</option>
                {#each weaponMounts as mount}
                  <option value={mount.id}>{mount.id}</option>
                {/each}
              </select>
            </label>
          </div>
          <button on:click={() => removeTrack(String(track.contact_id))}>REMOVE</button>
        </div>
      {/each}
    {/if}
  </div>
</Panel>

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .toolbar,
  .assignments {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-sm);
  }

  .track-card {
    display: grid;
    gap: 8px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
  }

  .header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  label {
    display: grid;
    gap: 6px;
  }

  span,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  strong {
    font-family: var(--font-mono);
  }
</style>
