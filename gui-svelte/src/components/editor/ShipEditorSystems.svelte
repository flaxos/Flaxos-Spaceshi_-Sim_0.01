<script lang="ts">
  export let systemsConfig: Record<string, any>;
  export let weaponMounts: any[];

  // ── System definitions ──────────────────────────────────────────────────────
  type FieldDef = {
    key: string;
    label: string;
    type: "number" | "select" | "checkbox";
    options?: string[];
    unit?: string;
    step?: number;
    min?: number;
  };

  type SystemDef = {
    label: string;
    fields: FieldDef[];
  };

  const SYSTEM_DEFS: Record<string, SystemDef> = {
    propulsion: {
      label: "Propulsion",
      fields: [
        { key: "max_thrust", label: "Max Thrust", type: "number", unit: "kN", step: 10, min: 0 },
        { key: "isp", label: "Isp", type: "number", unit: "s", step: 100, min: 0 },
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 5, min: 0 },
        { key: "drive_type", label: "Drive Type", type: "select",
          options: ["epstein", "chemical", "ion", "nuclear_thermal"] },
      ],
    },
    rcs: {
      label: "RCS",
      fields: [
        { key: "max_torque", label: "Max Torque", type: "number", unit: "Nm", step: 1, min: 0 },
        { key: "attitude_rate", label: "Attitude Rate", type: "number", unit: "°/s", step: 1, min: 0 },
        { key: "thruster_count", label: "Thrusters", type: "number", step: 1, min: 1 },
      ],
    },
    sensors: {
      label: "Sensors",
      fields: [
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 1, min: 0 },
        { key: "passive.range", label: "Passive Range", type: "number", unit: "km", step: 1000, min: 0 },
        { key: "active.scan_range", label: "Active Range", type: "number", unit: "km", step: 1000, min: 0 },
        { key: "active.cooldown_time", label: "Cooldown", type: "number", unit: "s", step: 0.5, min: 0 },
        { key: "signature_base", label: "Signature", type: "number", step: 0.1, min: 0 },
      ],
    },
    navigation: {
      label: "Navigation",
      fields: [
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 1, min: 0 },
      ],
    },
    targeting: {
      label: "Targeting",
      fields: [
        { key: "lock_time", label: "Lock Time", type: "number", unit: "s", step: 0.5, min: 0 },
        { key: "lock_range", label: "Lock Range", type: "number", unit: "km", step: 1000, min: 0 },
      ],
    },
    combat: {
      label: "Combat",
      fields: [
        { key: "railguns", label: "Railguns", type: "number", step: 1, min: 0 },
        { key: "pdcs", label: "PDCs", type: "number", step: 1, min: 0 },
        { key: "torpedoes", label: "Torpedo Tubes", type: "number", step: 1, min: 0 },
        { key: "torpedo_capacity", label: "Torpedo Cap.", type: "number", step: 1, min: 0 },
      ],
    },
    ecm: {
      label: "ECM",
      fields: [
        { key: "jammer_power", label: "Jammer Power", type: "number", unit: "W", step: 1000, min: 0 },
        { key: "chaff_count", label: "Chaff", type: "number", step: 1, min: 0 },
        { key: "flare_count", label: "Flares", type: "number", step: 1, min: 0 },
      ],
    },
    power_management: {
      label: "Power Management",
      fields: [
        { key: "primary.output", label: "Primary Bus", type: "number", unit: "kW", step: 5, min: 0 },
        { key: "secondary.output", label: "Secondary Bus", type: "number", unit: "kW", step: 5, min: 0 },
        { key: "tertiary.output", label: "Tertiary Bus", type: "number", unit: "kW", step: 5, min: 0 },
      ],
    },
    fleet_coord: {
      label: "Fleet Coordination",
      fields: [
        { key: "command_capable", label: "Command Capable", type: "checkbox" },
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 1, min: 0 },
      ],
    },
    comms: {
      label: "Comms",
      fields: [
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 1, min: 0 },
      ],
    },
    science: {
      label: "Science",
      fields: [
        { key: "power_draw", label: "Power Draw", type: "number", unit: "kW", step: 1, min: 0 },
      ],
    },
  };

  const WEAPON_TYPES = ["railgun", "pdc", "torpedo", "missile"] as const;
  const MOUNT_SECTIONS = [
    "fore", "aft", "port", "starboard", "dorsal", "ventral",
    "fore_dorsal", "fore_ventral", "midship_dorsal", "midship_port", "midship_starboard",
    "aft_dorsal", "aft_ventral", "fore_port", "fore_starboard",
  ] as const;

  // Track which systems are expanded
  let expanded: Record<string, boolean> = {};

  // ── Nested value helpers ─────────────────────────────────────────────────────

  function getNested(obj: any, path: string): any {
    return path.split(".").reduce((o, k) => o?.[k], obj);
  }

  function setNestedImmutable(obj: any, path: string, value: any): any {
    const parts = path.split(".");
    if (parts.length === 1) return { ...obj, [parts[0]]: value };
    return {
      ...obj,
      [parts[0]]: setNestedImmutable(obj?.[parts[0]] ?? {}, parts.slice(1).join("."), value),
    };
  }

  // ── System handlers ──────────────────────────────────────────────────────────

  function toggleSystem(sysId: string) {
    const current = systemsConfig[sysId]?.enabled ?? false;
    systemsConfig = {
      ...systemsConfig,
      [sysId]: { ...(systemsConfig[sysId] ?? {}), enabled: !current },
    };
    if (!current) expanded = { ...expanded, [sysId]: true };
  }

  function toggleExpand(sysId: string) {
    expanded = { ...expanded, [sysId]: !expanded[sysId] };
  }

  function updateSystemField(sysId: string, fieldKey: string, rawValue: string, fieldType: string) {
    let value: any = rawValue;
    if (fieldType === "number") value = parseFloat(rawValue) || 0;
    if (fieldType === "checkbox") value = (rawValue as any) === true || rawValue === "true";

    const updated = setNestedImmutable(systemsConfig[sysId] ?? {}, fieldKey, value);
    systemsConfig = { ...systemsConfig, [sysId]: updated };
  }

  // ── Weapon mount handlers ────────────────────────────────────────────────────

  let mountIdCounter = 0;

  function addMount() {
    mountIdCounter += 1;
    weaponMounts = [
      ...weaponMounts,
      {
        mount_id: `mount_${mountIdCounter}`,
        weapon_type: "railgun",
        placement: { section: "fore", position: { x: 0, y: 0, z: 0 } },
        firing_arc: { azimuth_min: -30, azimuth_max: 30, elevation_min: -20, elevation_max: 20 },
      },
    ];
  }

  function removeMount(idx: number) {
    weaponMounts = weaponMounts.filter((_, i) => i !== idx);
  }

  function updateMount(idx: number, key: string, value: any) {
    weaponMounts = weaponMounts.map((m, i) => {
      if (i !== idx) return m;
      if (key === "section") {
        return { ...m, placement: { ...m.placement, section: value } };
      }
      return { ...m, [key]: value };
    });
  }
</script>

<div class="systems-editor">
  <div class="section-title">SYSTEMS</div>

  {#each Object.entries(SYSTEM_DEFS) as [sysId, def]}
    {@const sysData = systemsConfig[sysId] ?? {}}
    {@const isEnabled = sysData.enabled ?? false}
    {@const isExpanded = expanded[sysId] ?? false}

    <div class="system-row" class:enabled={isEnabled}>
      <div class="system-header">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={isEnabled}
            on:change={() => toggleSystem(sysId)}
          />
          <span class="system-name">{def.label}</span>
        </label>
        {#if isEnabled}
          <button
            class="expand-btn"
            type="button"
            on:click={() => toggleExpand(sysId)}
            title="{isExpanded ? 'Collapse' : 'Expand'}"
          >
            {isExpanded ? "▲" : "▼"}
          </button>
        {/if}
      </div>

      {#if isEnabled && isExpanded}
        <div class="system-fields">
          {#each def.fields as field}
            <label class="field-row">
              <span class="field-label">
                {field.label}{field.unit ? ` (${field.unit})` : ""}
              </span>
              {#if field.type === "select"}
                <select
                  class="field-select"
                  value={getNested(sysData, field.key) ?? (field.options?.[0] ?? "")}
                  on:change={(e) => updateSystemField(sysId, field.key, e.currentTarget.value, "select")}
                >
                  {#each field.options ?? [] as opt}
                    <option value={opt}>{opt}</option>
                  {/each}
                </select>
              {:else if field.type === "checkbox"}
                <input
                  type="checkbox"
                  checked={getNested(sysData, field.key) ?? false}
                  on:change={(e) => updateSystemField(sysId, field.key, String(e.currentTarget.checked), "checkbox")}
                />
              {:else}
                <input
                  type="number"
                  class="field-input"
                  value={getNested(sysData, field.key) ?? 0}
                  min={field.min ?? 0}
                  step={field.step ?? 1}
                  on:change={(e) => updateSystemField(sysId, field.key, e.currentTarget.value, "number")}
                />
              {/if}
            </label>
          {/each}
        </div>
      {/if}
    </div>
  {/each}

  <!-- Weapon Mounts -->
  <div class="section-title" style="margin-top: var(--space-xs)">WEAPON MOUNTS</div>

  {#each weaponMounts as mount, idx}
    <div class="mount-row">
      <input
        type="text"
        class="field-input mount-id"
        value={mount.mount_id}
        placeholder="mount_id"
        on:change={(e) => updateMount(idx, "mount_id", e.currentTarget.value)}
      />
      <select
        class="field-select"
        value={mount.weapon_type}
        on:change={(e) => updateMount(idx, "weapon_type", e.currentTarget.value)}
      >
        {#each WEAPON_TYPES as wt}
          <option value={wt}>{wt}</option>
        {/each}
      </select>
      <select
        class="field-select"
        value={mount.placement?.section ?? "fore"}
        on:change={(e) => updateMount(idx, "section", e.currentTarget.value)}
      >
        {#each MOUNT_SECTIONS as sec}
          <option value={sec}>{sec.replace(/_/g, " ")}</option>
        {/each}
      </select>
      <button class="remove-btn" type="button" on:click={() => removeMount(idx)} title="Remove mount">
        ×
      </button>
    </div>
  {/each}

  <button class="add-btn" type="button" on:click={addMount}>+ ADD MOUNT</button>
</div>

<style>
  .systems-editor {
    display: flex;
    flex-direction: column;
    gap: 3px;
    overflow-y: auto;
    padding-right: 2px;
  }

  .section-title {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--tier-accent, var(--text-secondary));
    padding: 4px 0;
    border-bottom: 1px solid var(--border-default);
  }

  .system-row {
    border: 1px solid var(--border-default);
    border-radius: 3px;
    overflow: hidden;
  }

  .system-row.enabled {
    border-color: rgba(var(--tier-accent-rgb, 68,136,255), 0.35);
  }

  .system-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    background: var(--bg-panel);
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }

  .system-name {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-secondary);
    letter-spacing: 0.05em;
  }

  .system-row.enabled .system-name { color: var(--text-primary); }

  .expand-btn {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.6rem;
    padding: 2px 4px;
  }

  .system-fields {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px 8px;
    background: rgba(255,255,255,0.02);
    border-top: 1px solid var(--border-default);
  }

  .field-row {
    display: grid;
    grid-template-columns: 130px 1fr;
    align-items: center;
    gap: 6px;
  }

  .field-label {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-dim);
  }

  .field-input,
  .field-select {
    background: var(--bg-input, rgba(255,255,255,0.04));
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 3px 6px;
    width: 100%;
    box-sizing: border-box;
  }

  .field-input:focus,
  .field-select:focus {
    outline: none;
    border-color: var(--tier-accent, var(--hud-primary));
  }

  /* Weapon mounts */
  .mount-row {
    display: grid;
    grid-template-columns: 100px 90px 1fr 24px;
    gap: 4px;
    align-items: center;
    padding: 3px 0;
  }

  .mount-id { font-size: 0.65rem; }

  .remove-btn {
    background: none;
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--status-critical, #ff4444);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0;
    height: 22px;
    width: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .add-btn {
    margin-top: 4px;
    padding: 5px 10px;
    background: rgba(255,255,255,0.03);
    border: 1px dashed var(--border-default);
    border-radius: 3px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    cursor: pointer;
    width: 100%;
    text-align: left;
    letter-spacing: 0.04em;
  }

  .add-btn:hover {
    border-color: var(--tier-accent, var(--hud-primary));
    color: var(--text-primary);
  }
</style>
