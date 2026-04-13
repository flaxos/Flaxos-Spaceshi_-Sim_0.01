<script lang="ts">
  import { onMount } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { isCommandRejected, describeCommandFailure } from "../../lib/ws/commandResponse.js";
  import ShipEditorHull from "./ShipEditorHull.svelte";
  import ShipEditorSystems from "./ShipEditorSystems.svelte";
  import ShipEditorPreview from "./ShipEditorPreview.svelte";

  // ── State ────────────────────────────────────────────────────────────────────
  let shipClasses: any[] = [];
  let selectedId: string | null = null;
  let isNew = false;
  let statusMsg = "";
  let statusType: "idle" | "success" | "error" | "saving" = "idle";
  let statusTimer: ReturnType<typeof setTimeout> | null = null;

  // Config slices (owned by this coordinator)
  let hullConfig: Record<string, any> = createEmptyHull();
  let systemsConfig: Record<string, any> = {};
  let weaponMounts: any[] = [];
  let damageModel: Record<string, any> = {};

  $: fullConfig = {
    ...hullConfig,
    systems: systemsConfig,
    weapon_mounts: weaponMounts,
    damage_model: damageModel,
  };

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function deepClone<T>(obj: T): T {
    return JSON.parse(JSON.stringify(obj ?? {}));
  }

  function createEmptyHull(): Record<string, any> {
    return {
      class_id: "",
      class_name: "",
      description: "",
      dimensions: { length_m: 50, beam_m: 10, draft_m: 8 },
      crew_complement: { minimum: 2, standard: 4, maximum: 8 },
      mass: { dry_mass: 100000, max_fuel: 50000, max_hull_integrity: 1000 },
      armor: Object.fromEntries(
        ["fore", "aft", "port", "starboard", "dorsal", "ventral"].map((s) => [
          s,
          { thickness_cm: 2, material: "composite_cermet" },
        ])
      ),
    };
  }

  function showStatus(msg: string, type: typeof statusType = "success") {
    statusMsg = msg;
    statusType = type;
    if (statusTimer) clearTimeout(statusTimer);
    if (type !== "saving") {
      statusTimer = setTimeout(() => { statusMsg = ""; statusType = "idle"; }, 4000);
    }
  }

  // ── Load class list ──────────────────────────────────────────────────────────

  async function loadClasses() {
    try {
      const res = await wsClient.send("get_ship_classes_full", {}) as any;
      if (isCommandRejected(res)) {
        showStatus(describeCommandFailure(res, "Failed to load ship classes"), "error");
        return;
      }
      shipClasses = res.ship_classes ?? [];
    } catch {
      showStatus("Connection error loading ship classes", "error");
    }
  }

  // ── Select / New ─────────────────────────────────────────────────────────────

  function selectClass(cls: any) {
    const cloned = deepClone(cls);
    selectedId = cloned.class_id;
    isNew = false;

    // Peel apart the top-level config into slices
    const { systems, weapon_mounts, damage_model, ...hull } = cloned;
    hullConfig    = hull;
    systemsConfig = systems ?? {};
    weaponMounts  = weapon_mounts ?? [];
    damageModel   = damage_model ?? {};
  }

  function newShip() {
    selectedId = null;
    isNew = true;
    hullConfig    = createEmptyHull();
    systemsConfig = {};
    weaponMounts  = [];
    damageModel   = {};
    statusMsg = "";
  }

  // ── Validate ─────────────────────────────────────────────────────────────────

  function validate(): string | null {
    if (!hullConfig.class_id) return "Class ID is required";
    if (!/^[a-z][a-z0-9_]*$/.test(hullConfig.class_id)) {
      return "Class ID must be lowercase alphanumeric (underscores allowed)";
    }
    if (!hullConfig.class_name?.trim()) return "Class name is required";
    if ((hullConfig.mass?.dry_mass ?? 0) <= 0) return "Dry mass must be > 0";
    return null;
  }

  // ── Save ─────────────────────────────────────────────────────────────────────

  async function save() {
    const err = validate();
    if (err) { showStatus(err, "error"); return; }

    showStatus("Saving…", "saving");
    try {
      const res = await wsClient.send("save_ship_class", { config: fullConfig }) as any;
      if (isCommandRejected(res)) {
        showStatus(describeCommandFailure(res, "Save failed"), "error");
        return;
      }
      showStatus(`Saved: ${hullConfig.class_id}`, "success");
      await loadClasses();
      // Keep the current selection
      selectedId = hullConfig.class_id;
    } catch {
      showStatus("Connection error — save failed", "error");
    }
  }

  // ── Export JSON ───────────────────────────────────────────────────────────────

  function exportJson() {
    const blob = new Blob([JSON.stringify(fullConfig, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${hullConfig.class_id || "ship_class"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  onMount(loadClasses);
</script>

<div class="ship-editor">
  <!-- Sidebar: class list -->
  <aside class="class-list">
    <button class="new-btn" type="button" on:click={newShip}>+ NEW</button>
    <div class="list-scroll">
      {#each shipClasses as cls}
        <button
          class="class-btn"
          class:selected={cls.class_id === selectedId && !isNew}
          type="button"
          on:click={() => selectClass(cls)}
          title={cls.description ?? cls.class_name}
        >
          <span class="class-name">{cls.class_name}</span>
          <span class="class-id">{cls.class_id}</span>
        </button>
      {/each}
      {#if shipClasses.length === 0}
        <div class="list-empty">No classes loaded</div>
      {/if}
    </div>
  </aside>

  <!-- Main editor area -->
  <div class="editor-main">
    {#if selectedId !== null || isNew}
      <div class="editor-panes">
        <div class="pane">
          <ShipEditorHull bind:hullConfig />
        </div>
        <div class="pane">
          <ShipEditorSystems bind:systemsConfig bind:weaponMounts />
        </div>
        <div class="pane">
          <ShipEditorPreview {fullConfig} bind:damageModel />
        </div>
      </div>

      <div class="action-bar">
        <button class="action-btn primary" type="button" on:click={save}>SAVE</button>
        <button class="action-btn" type="button" on:click={exportJson}>EXPORT JSON</button>
        {#if statusMsg}
          <span class="status-msg status-{statusType}">{statusMsg}</span>
        {/if}
      </div>
    {:else}
      <div class="select-prompt">
        Select a ship class to edit, or click <strong>+ NEW</strong> to create one.
      </div>
    {/if}
  </div>
</div>

<style>
  .ship-editor {
    display: grid;
    grid-template-columns: 180px 1fr;
    height: 100%;
    overflow: hidden;
  }

  /* Sidebar */
  .class-list {
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border-default);
    overflow: hidden;
  }

  .new-btn {
    flex-shrink: 0;
    padding: 8px 12px;
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
    border: none;
    border-bottom: 1px solid var(--border-default);
    color: var(--tier-accent, var(--hud-primary));
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    cursor: pointer;
    text-align: left;
  }

  .new-btn:hover {
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.18);
  }

  .list-scroll {
    flex: 1;
    overflow-y: auto;
    scrollbar-width: thin;
  }

  .class-btn {
    display: flex;
    flex-direction: column;
    width: 100%;
    padding: 7px 10px;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    color: var(--text-secondary);
    text-align: left;
    cursor: pointer;
    gap: 2px;
  }

  .class-btn:hover { background: var(--bg-hover); }

  .class-btn.selected {
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
    border-left: 2px solid var(--tier-accent, var(--hud-primary));
  }

  .class-name {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-primary);
  }

  .class-id {
    font-family: var(--font-mono);
    font-size: 0.55rem;
    color: var(--text-dim);
    letter-spacing: 0.03em;
  }

  .list-empty {
    padding: 12px 10px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-dim);
  }

  /* Main area */
  .editor-main {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .editor-panes {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
    min-height: 0;
  }

  .pane {
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .action-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 8px var(--space-sm);
    border-top: 1px solid var(--border-default);
    background: var(--bg-panel);
  }

  .action-btn {
    padding: 6px 14px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.04);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
  }

  .action-btn:hover {
    background: rgba(255,255,255,0.08);
    color: var(--text-primary);
  }

  .action-btn.primary {
    border-color: rgba(var(--tier-accent-rgb, 68,136,255), 0.6);
    color: var(--tier-accent, var(--hud-primary));
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.1);
  }

  .action-btn.primary:hover {
    background: rgba(var(--tier-accent-rgb, 68,136,255), 0.2);
  }

  .status-msg {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    letter-spacing: 0.04em;
  }

  .status-success { color: var(--status-nominal, #00ff88); }
  .status-error   { color: var(--status-critical, #ff4444); }
  .status-saving  { color: var(--text-dim); }

  .select-prompt {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--text-dim);
    letter-spacing: 0.04em;
  }

  @media (max-width: 1100px) {
    .editor-panes { grid-template-columns: 1fr; overflow-y: auto; }
  }
</style>
