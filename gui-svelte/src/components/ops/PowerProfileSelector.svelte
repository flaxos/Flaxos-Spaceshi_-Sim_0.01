<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { asRecord, toStringValue } from "./opsData.js";

  interface PowerProfileCard {
    name: string;
    description: string;
  }

  let profiles: PowerProfileCard[] = [];
  let activeProfile = "";
  let selectedProfile = "";
  let feedback = "";
  let pollHandle: number | null = null;

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 10000);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("get_power_profiles", {});
      const record = asRecord(response);
      const definitions = asRecord(record?.definitions) ?? {};
      const source = Array.isArray(record?.profiles) ? record?.profiles : Object.keys(definitions);
      activeProfile = toStringValue(record?.active_profile);
      if (!selectedProfile) selectedProfile = activeProfile;
      profiles = source.map((item) => {
        const name = String(item);
        const definition = asRecord(definitions[name]) ?? {};
        return {
          name,
          description: toStringValue(definition.description, "Preset power routing profile"),
        };
      });
    } catch {
      // best effort
    }
  }

  async function applyProfile(name: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("set_power_profile", { profile: name });
      activeProfile = name;
      selectedProfile = name;
      feedback = `${name} applied`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Profile apply failed";
    }
  }
</script>

<Panel title="Power Profiles" domain="power" priority="secondary" className="power-profile-selector-panel">
  <div class="shell">
    {#if profiles.length === 0}
      <div class="empty">No power profiles available.</div>
    {:else}
      {#each profiles as profile}
        <button
          type="button"
          class:selected={profile.name === selectedProfile}
          class:active={profile.name === activeProfile}
          on:click={() => selectedProfile = profile.name}
        >
          <strong>{profile.name.toUpperCase()}</strong>
          <span>{profile.description}</span>
        </button>
      {/each}
      <button
        class="apply"
        type="button"
        disabled={!selectedProfile || selectedProfile === activeProfile}
        on:click={() => applyProfile(selectedProfile)}
      >
        APPLY PROFILE
      </button>
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

  button,
  .empty,
  .feedback {
    display: grid;
    gap: 6px;
    width: 100%;
    text-align: left;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  button.selected {
    border-color: rgba(var(--tier-accent-rgb), 0.5);
  }

  button.active {
    background: rgba(0, 255, 136, 0.08);
    border-color: rgba(0, 255, 136, 0.35);
  }

  button.apply {
    text-align: center;
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  span,
  .empty,
  .feedback {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
