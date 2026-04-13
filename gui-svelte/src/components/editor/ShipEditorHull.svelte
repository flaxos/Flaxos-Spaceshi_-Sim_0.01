<script lang="ts">
  export let hullConfig: Record<string, any>;

  const ARMOR_SECTIONS = ["fore", "aft", "port", "starboard", "dorsal", "ventral"] as const;
  const ARMOR_MATERIALS = [
    "composite_cermet",
    "steel_composite",
    "station_composite",
    "asteroid_rock",
  ] as const;

  // Auto-slug class_id from class_name (only when class_id looks auto-generated)
  let idManuallyEdited = false;

  function slugify(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "");
  }

  function onClassNameInput(e: Event) {
    const name = (e.target as HTMLInputElement).value;
    hullConfig = { ...hullConfig, class_name: name };
    if (!idManuallyEdited) {
      hullConfig = { ...hullConfig, class_name: name, class_id: slugify(name) };
    }
  }

  function onClassIdInput(e: Event) {
    idManuallyEdited = true;
    hullConfig = { ...hullConfig, class_id: (e.target as HTMLInputElement).value };
  }

  function setDescription(e: Event) {
    hullConfig = { ...hullConfig, description: (e.target as HTMLTextAreaElement).value };
  }

  function setDimension(key: string, e: Event) {
    hullConfig = {
      ...hullConfig,
      dimensions: {
        ...hullConfig.dimensions,
        [key]: parseFloat((e.target as HTMLInputElement).value) || 0,
      },
    };
  }

  function setCrew(key: string, e: Event) {
    hullConfig = {
      ...hullConfig,
      crew_complement: {
        ...hullConfig.crew_complement,
        [key]: parseInt((e.target as HTMLInputElement).value) || 0,
      },
    };
  }

  function setMass(key: string, e: Event) {
    hullConfig = {
      ...hullConfig,
      mass: {
        ...hullConfig.mass,
        [key]: parseFloat((e.target as HTMLInputElement).value) || 0,
      },
    };
  }

  function setArmorThickness(section: string, e: Event) {
    hullConfig = {
      ...hullConfig,
      armor: {
        ...hullConfig.armor,
        [section]: {
          ...(hullConfig.armor?.[section] ?? {}),
          thickness_cm: parseFloat((e.target as HTMLInputElement).value) || 0,
        },
      },
    };
  }

  function setArmorMaterial(section: string, e: Event) {
    hullConfig = {
      ...hullConfig,
      armor: {
        ...hullConfig.armor,
        [section]: {
          ...(hullConfig.armor?.[section] ?? {}),
          material: (e.target as HTMLSelectElement).value,
        },
      },
    };
  }
</script>

<div class="hull-editor">
  <div class="section-title">HULL</div>

  <!-- Identity -->
  <fieldset class="field-group">
    <legend>Identity</legend>
    <label class="field-row">
      <span class="field-label">Class Name</span>
      <input
        type="text"
        class="field-input"
        value={hullConfig.class_name ?? ""}
        on:input={onClassNameInput}
        placeholder="e.g. Corvette"
      />
    </label>
    <label class="field-row">
      <span class="field-label">Class ID</span>
      <input
        type="text"
        class="field-input monospace"
        value={hullConfig.class_id ?? ""}
        on:input={onClassIdInput}
        placeholder="e.g. corvette"
      />
    </label>
    <label class="field-row">
      <span class="field-label">Description</span>
      <textarea
        class="field-textarea"
        rows="3"
        value={hullConfig.description ?? ""}
        on:input={setDescription}
        placeholder="Brief description of the ship class"
      ></textarea>
    </label>
  </fieldset>

  <!-- Dimensions -->
  <fieldset class="field-group">
    <legend>Dimensions (m)</legend>
    <label class="field-row">
      <span class="field-label">Length</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.dimensions?.length_m ?? 50}
        min="1"
        step="0.5"
        on:change={(e) => setDimension("length_m", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Beam</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.dimensions?.beam_m ?? 10}
        min="1"
        step="0.5"
        on:change={(e) => setDimension("beam_m", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Draft</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.dimensions?.draft_m ?? 8}
        min="1"
        step="0.5"
        on:change={(e) => setDimension("draft_m", e)}
      />
    </label>
  </fieldset>

  <!-- Crew -->
  <fieldset class="field-group">
    <legend>Crew Complement</legend>
    <label class="field-row">
      <span class="field-label">Minimum</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.crew_complement?.minimum ?? 1}
        min="1"
        on:change={(e) => setCrew("minimum", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Standard</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.crew_complement?.standard ?? 4}
        min="1"
        on:change={(e) => setCrew("standard", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Maximum</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.crew_complement?.maximum ?? 8}
        min="1"
        on:change={(e) => setCrew("maximum", e)}
      />
    </label>
  </fieldset>

  <!-- Mass -->
  <fieldset class="field-group">
    <legend>Mass (kg / t)</legend>
    <label class="field-row">
      <span class="field-label">Dry Mass</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.mass?.dry_mass ?? 100000}
        min="1"
        step="100"
        on:change={(e) => setMass("dry_mass", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Max Fuel</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.mass?.max_fuel ?? 50000}
        min="0"
        step="100"
        on:change={(e) => setMass("max_fuel", e)}
      />
    </label>
    <label class="field-row">
      <span class="field-label">Hull Integrity</span>
      <input
        type="number"
        class="field-input"
        value={hullConfig.mass?.max_hull_integrity ?? 1000}
        min="1"
        step="10"
        on:change={(e) => setMass("max_hull_integrity", e)}
      />
    </label>
  </fieldset>

  <!-- Armor -->
  <fieldset class="field-group">
    <legend>Armor</legend>
    <div class="armor-header">
      <span>Section</span>
      <span>Thickness (cm)</span>
      <span>Material</span>
    </div>
    {#each ARMOR_SECTIONS as section}
      {@const armorSection = hullConfig.armor?.[section] ?? { thickness_cm: 2, material: "composite_cermet" }}
      <div class="armor-row">
        <span class="armor-label">{section.toUpperCase()}</span>
        <div class="armor-slider-group">
          <input
            type="range"
            min="0"
            max="20"
            step="0.5"
            value={armorSection.thickness_cm}
            on:input={(e) => setArmorThickness(section, e)}
          />
          <span class="armor-value">{armorSection.thickness_cm.toFixed(1)}</span>
        </div>
        <select
          class="field-select"
          value={armorSection.material}
          on:change={(e) => setArmorMaterial(section, e)}
        >
          {#each ARMOR_MATERIALS as mat}
            <option value={mat}>{mat.replace(/_/g, " ")}</option>
          {/each}
        </select>
      </div>
    {/each}
  </fieldset>
</div>

<style>
  .hull-editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
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

  fieldset.field-group {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 6px 8px 8px;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  legend {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    text-transform: uppercase;
    padding: 0 4px;
  }

  .field-row {
    display: grid;
    grid-template-columns: 90px 1fr;
    align-items: center;
    gap: 6px;
  }

  .field-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-dim);
    white-space: nowrap;
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

  .field-input.monospace { letter-spacing: 0.03em; }

  .field-textarea {
    background: var(--bg-input, rgba(255,255,255,0.04));
    border: 1px solid var(--border-default);
    border-radius: 3px;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 4px 6px;
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
  }

  .field-textarea:focus { outline: none; border-color: var(--tier-accent, var(--hud-primary)); }

  .armor-header {
    display: grid;
    grid-template-columns: 80px 1fr 130px;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 0.55rem;
    color: var(--text-dim);
    letter-spacing: 0.08em;
    margin-bottom: 2px;
  }

  .armor-row {
    display: grid;
    grid-template-columns: 80px 1fr 130px;
    align-items: center;
    gap: 6px;
  }

  .armor-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
  }

  .armor-slider-group {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .armor-slider-group input[type="range"] {
    flex: 1;
    accent-color: var(--tier-accent, var(--hud-primary));
  }

  .armor-value {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-primary);
    min-width: 28px;
    text-align: right;
  }
</style>
