<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import {
    asRecord,
    extractShipState,
    formatDistance,
    getCombatState,
    getIncomingMunitions,
    getLockedTargetId,
    getMultiTrackState,
    getPdcMounts,
    getTacticalContacts,
    toNumber,
    toStringValue,
  } from "./tacticalData.js";
  import { addTrack, assignPdcTarget, firePdc, setPdcMode, setPdcPriority } from "./tacticalActions.js";

  export let embedded = false;

  const modes = [
    { label: "AUTO", value: "auto" },
    { label: "MANUAL", value: "manual" },
    { label: "NETWORK", value: "network" },
    { label: "PRIORITY", value: "priority" },
    { label: "HOLD", value: "hold_fire" },
  ];

  let modePending = false;
  let firingMounts = new Set<string>();
  let mountSelections: Record<string, string> = {};

  $: ship = extractShipState($gameState);
  $: combat = getCombatState(ship);
  $: multiTrack = getMultiTrackState(ship);
  $: contacts = getTacticalContacts(ship);
  $: lockedTargetId = getLockedTargetId(ship);
  $: incomingMunitions = getIncomingMunitions($gameState, ship);
  $: pdcMounts = getPdcMounts(ship);
  $: pdcAssignments = asRecord(multiTrack.pdcAssignments) ?? {};
  $: pdcEngagements = asRecord(combat.pdc_engagements) ?? {};
  $: pdcStats = asRecord(combat.pdc_stats) ?? {};
  $: trackedIds = new Set(
    (Array.isArray(multiTrack.tracks) ? multiTrack.tracks : [])
      .map((track) => toStringValue(asRecord(track)?.contact_id))
      .filter(Boolean),
  );
  $: mode = toStringValue(combat.pdc_mode, "auto");
  $: priorityTarget = Array.isArray(combat.pdc_priority_targets)
    ? toStringValue(combat.pdc_priority_targets[0])
    : "";
  $: mountSelections = syncSelections(mountSelections, pdcMounts.map((mount) => mount.id));

  const modeDescriptions: Record<string, string> = {
    auto: "Automatically engage incoming threats",
    manual: "PDC fires only on explicit command",
    network: "Coordinate engagement across all PDC mounts",
    priority: "Engage threat-board priority targets first",
    hold_fire: "PDC will not fire — all mounts safed",
  };

  function syncSelections(current: Record<string, string>, mountIds: string[]) {
    let changed = false;
    const next: Record<string, string> = {};
    for (const mountId of mountIds) {
      if (current[mountId] !== undefined) next[mountId] = current[mountId];
      if (!(mountId in current)) changed = true;
    }
    for (const mountId of Object.keys(current)) {
      if (!mountIds.includes(mountId)) changed = true;
    }
    return changed ? next : current;
  }

  function getAssignedTarget(mountId: string) {
    return toStringValue(
      mountSelections[mountId],
      toStringValue(
        pdcAssignments[mountId],
        toStringValue(
          pdcEngagements[mountId],
          toStringValue($selectedTacticalTargetId, lockedTargetId),
        ),
      ),
    );
  }

  function assignmentLabel(targetId: string) {
    if (!targetId) return "NO TRACK ASSIGNED";
    return trackedIds.has(targetId) ? `TRACK ${targetId}` : `LOCK ${targetId}`;
  }

  async function ensureTracked(contactId: string) {
    if (!contactId || trackedIds.has(contactId)) return;
    try {
      await addTrack(contactId);
    } catch {
      // Best effort; fire path can still fall back to the primary lock.
    }
  }

  async function setMode(next: string) {
    if (modePending || mode === next) return;
    modePending = true;
    try {
      await setPdcMode(next);
    } finally {
      modePending = false;
    }
  }

  async function applyPriority(event: Event) {
    const targetId = (event.currentTarget as HTMLSelectElement).value;
    if (!targetId) return;
    await setPdcPriority([targetId]);
  }

  async function assignMount(mountId: string, targetId: string) {
    mountSelections = {
      ...mountSelections,
      [mountId]: targetId,
    };
    if (!targetId) return;
    selectedTacticalTargetId.set(targetId);
    await ensureTracked(targetId);
    await assignPdcTarget(mountId, targetId);
  }

  async function fireMount(mountId: string) {
    if (firingMounts.has(mountId) || mode !== "manual") return;
    const targetId = getAssignedTarget(mountId);
    const next = new Set(firingMounts);
    next.add(mountId);
    firingMounts = next;
    try {
      if (targetId) {
        await ensureTracked(targetId);
        await assignPdcTarget(mountId, targetId);
      }
      await firePdc({ mountId, targetId: targetId || undefined });
    } finally {
      const pending = new Set(firingMounts);
      pending.delete(mountId);
      firingMounts = pending;
    }
  }

  function mountReady(mountId: string) {
    const mount = pdcMounts.find((item) => item.id === mountId);
    return Boolean(mount && mount.enabled && mount.ammo > 0 && !mount.reloading);
  }

  function statValue(mountId: string, key: string) {
    const stats = asRecord(pdcStats[mountId]);
    return Math.round(toNumber(stats?.[key], 0));
  }
</script>

{#if embedded}
  <div class="shell embedded-shell">
    <div class="status-strip">
      <div>
        <span>Mode</span>
        <strong>{mode.replaceAll("_", " ").toUpperCase()}</strong>
      </div>
      <div>
        <span>Threats</span>
        <strong>{incomingMunitions.length}</strong>
      </div>
      <div>
        <span>Tracked</span>
        <strong>{multiTrack.trackCount}</strong>
      </div>
    </div>

    <div class="mode-grid">
      {#each modes as item}
        <button
          class:selected={mode === item.value}
          disabled={modePending}
          title={modeDescriptions[item.value] ?? item.label}
          type="button"
          on:click={() => setMode(item.value)}
        >{item.label}</button>
      {/each}
    </div>

    <label>
      <span>Priority Threat</span>
      <select value={priorityTarget} on:change={applyPriority}>
        <option value="">Select incoming threat</option>
        {#each incomingMunitions as munition}
          <option value={munition.id}>
            {munition.id} · {munition.munitionType.toUpperCase()} · {formatDistance(munition.distance)}
          </option>
        {/each}
      </select>
    </label>

    <div class="mount-list">
      {#each pdcMounts as mount}
        {@const assignedTarget = getAssignedTarget(mount.id)}
        <div class="mount-card">
          <div class="mount-head">
            <div>
              <strong>{mount.label}</strong>
              <p>{mount.status.toUpperCase()} · {mount.ammo}/{mount.ammoCapacity || mount.ammo} RDS</p>
            </div>
            <div class="stat-pair">
              <span>{statValue(mount.id, "shots_fired")} SH</span>
              <span>{statValue(mount.id, "hits")} HIT</span>
            </div>
          </div>

          <label>
            <span>Assigned Track</span>
            <select value={assignedTarget} on:change={(event) => assignMount(mount.id, (event.currentTarget as HTMLSelectElement).value)}>
              <option value="">Locked / selected target</option>
              {#if incomingMunitions.length > 0}
                <optgroup label="Incoming Threats">
                  {#each incomingMunitions as munition}
                    <option value={munition.id}>
                      {munition.id} · {munition.munitionType.toUpperCase()}
                    </option>
                  {/each}
                </optgroup>
              {/if}
              <optgroup label="Sensor Contacts">
                {#each contacts as contact}
                  <option value={contact.id}>
                    {contact.id} · {contact.classification} {trackedIds.has(contact.id) ? "· TRACKED" : ""}
                  </option>
                {/each}
              </optgroup>
            </select>
          </label>

          <div class="mount-actions">
            <span class="assignment">{assignmentLabel(assignedTarget)}</span>
            <button
              class="fire-btn"
              disabled={mode !== "manual" || !mountReady(mount.id) || firingMounts.has(mount.id)}
              on:click={() => fireMount(mount.id)}
            >
              {firingMounts.has(mount.id) ? "FIRING…" : "FIRE"}
            </button>
          </div>
        </div>
      {/each}
    </div>
  </div>
{:else}
  <Panel title="PDC Control" domain="weapons" priority="secondary" className="pdc-control-panel">
    <div class="shell">
      <div class="status-strip">
        <div>
          <span>Mode</span>
          <strong>{mode.replaceAll("_", " ").toUpperCase()}</strong>
        </div>
        <div>
          <span>Threats</span>
          <strong>{incomingMunitions.length}</strong>
        </div>
        <div>
          <span>Tracked</span>
          <strong>{multiTrack.trackCount}</strong>
        </div>
      </div>

      <div class="mode-grid">
        {#each modes as item}
          <button
            class:selected={mode === item.value}
            disabled={modePending}
            title={modeDescriptions[item.value] ?? item.label}
            type="button"
            on:click={() => setMode(item.value)}
          >{item.label}</button>
        {/each}
      </div>

      <label>
        <span>Priority Threat</span>
        <select value={priorityTarget} on:change={applyPriority}>
          <option value="">Select incoming threat</option>
          {#each incomingMunitions as munition}
            <option value={munition.id}>
              {munition.id} · {munition.munitionType.toUpperCase()} · {formatDistance(munition.distance)}
            </option>
          {/each}
        </select>
      </label>

      <div class="mount-list">
        {#each pdcMounts as mount}
          {@const assignedTarget = getAssignedTarget(mount.id)}
          <div class="mount-card">
            <div class="mount-head">
              <div>
                <strong>{mount.label}</strong>
                <p>{mount.status.toUpperCase()} · {mount.ammo}/{mount.ammoCapacity || mount.ammo} RDS</p>
              </div>
              <div class="stat-pair">
                <span>{statValue(mount.id, "shots_fired")} SH</span>
                <span>{statValue(mount.id, "hits")} HIT</span>
              </div>
            </div>

            <label>
              <span>Assigned Track</span>
              <select value={assignedTarget} on:change={(event) => assignMount(mount.id, (event.currentTarget as HTMLSelectElement).value)}>
                <option value="">Locked / selected target</option>
                {#if incomingMunitions.length > 0}
                  <optgroup label="Incoming Threats">
                    {#each incomingMunitions as munition}
                      <option value={munition.id}>
                        {munition.id} · {munition.munitionType.toUpperCase()}
                      </option>
                    {/each}
                  </optgroup>
                {/if}
                <optgroup label="Sensor Contacts">
                  {#each contacts as contact}
                    <option value={contact.id}>
                      {contact.id} · {contact.classification} {trackedIds.has(contact.id) ? "· TRACKED" : ""}
                    </option>
                  {/each}
                </optgroup>
              </select>
            </label>

            <div class="mount-actions">
              <span class="assignment">{assignmentLabel(assignedTarget)}</span>
              <button
                class="fire-btn"
                disabled={mode !== "manual" || !mountReady(mount.id) || firingMounts.has(mount.id)}
                on:click={() => fireMount(mount.id)}
              >
                {firingMounts.has(mount.id) ? "FIRING…" : "FIRE"}
              </button>
            </div>
          </div>
        {/each}
      </div>
    </div>
  </Panel>
{/if}

<style>
  .shell {
    display: grid;
    gap: var(--space-sm);
    padding: var(--space-sm);
  }

  .embedded-shell {
    padding: 0;
  }

  .status-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-sm);
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
  }

  .status-strip div,
  .mount-card,
  label {
    display: grid;
    gap: 6px;
  }

  .status-strip span,
  span,
  .mount-head p,
  .assignment {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .status-strip strong,
  .mount-head strong,
  .stat-pair span {
    font-family: var(--font-mono);
  }

  .mode-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
  }

  .mode-grid button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .mount-list {
    display: grid;
    gap: var(--space-sm);
  }

  .mount-card {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.02);
  }

  .mount-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: start;
  }

  .mount-head p {
    margin: 0;
  }

  .stat-pair {
    display: flex;
    gap: 8px;
  }

  .mount-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .assignment {
    flex: 1;
  }

  .fire-btn {
    min-width: 88px;
    border-color: rgba(232, 48, 48, 0.4);
    background: rgba(192, 48, 48, 0.18);
    color: var(--crit);
  }

  @media (max-width: 720px) {
    .status-strip,
    .mode-grid {
      grid-template-columns: 1fr;
    }

    .mount-actions,
    .mount-head {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
