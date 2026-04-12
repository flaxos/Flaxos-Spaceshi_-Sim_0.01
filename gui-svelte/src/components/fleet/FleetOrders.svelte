<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import { autoFleetProposals } from "./fleetData.js";

  const SIMPLE_ORDERS = [
    { label: "INTERCEPT", command: "intercept" },
    { label: "HOLD", command: "hold" },
    { label: "FLANK", command: "intercept" },
    { label: "RETREAT", command: "evasive" },
  ];

  let maneuver = "hold";
  let position = { x: 0, y: 0, z: 0 };
  let velocity = { x: 0, y: 0, z: 0 };
  let proposals: ReturnType<typeof autoFleetProposals> = [];
  let feedback = "";
  let pollHandle: number | null = null;

  $: rawTier = $tier === "raw";
  $: arcadeTier = $tier === "arcade";
  $: cpuAssistTier = $tier === "cpu-assist";

  onMount(() => {
    if (cpuAssistTier) {
      void refreshProposals();
      pollHandle = window.setInterval(() => void refreshProposals(), 3000);
    }
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
    };
  });

  async function refreshProposals() {
    try {
      const response = await wsClient.sendShipCommand("auto_fleet_status", {});
      proposals = autoFleetProposals(response);
    } catch {
      proposals = [];
    }
  }

  async function sendOrder(command = maneuver) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("fleet_maneuver", {
        maneuver: command,
        position,
        velocity,
      });
      feedback = `${command.toUpperCase()} ordered`;
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Fleet maneuver failed";
    }
  }

  async function reviewProposal(proposalId: string, approve: boolean) {
    try {
      await wsClient.sendShipCommand(approve ? "approve_fleet" : "deny_fleet", { proposal_id: proposalId });
      await refreshProposals();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Proposal review failed";
    }
  }
</script>

<Panel title="Fleet Orders" domain="weapons" priority={cpuAssistTier ? "primary" : "secondary"} className="fleet-orders-panel">
  <div class="shell">
    {#if cpuAssistTier}
      {#if proposals.length === 0}
        <div class="empty">No pending fleet proposals.</div>
      {:else}
        {#each proposals as proposal}
          <section class="proposal-card">
            <div class="head">
              <strong>{proposal.action.replaceAll("_", " ").toUpperCase()}</strong>
              <span>{Math.round(proposal.confidence * 100)}%</span>
            </div>
            <div class="reason">{proposal.reason}</div>
            <div class="button-row">
              <button type="button" on:click={() => reviewProposal(proposal.proposalId, true)}>APPROVE</button>
              <button class="secondary" type="button" on:click={() => reviewProposal(proposal.proposalId, false)}>DENY</button>
            </div>
          </section>
        {/each}
      {/if}
    {:else if arcadeTier}
      <div class="simple-grid">
        {#each SIMPLE_ORDERS as order}
          <button type="button" on:click={() => sendOrder(order.command)}>{order.label}</button>
        {/each}
      </div>
    {:else}
      <label class="field">
        <span>Maneuver</span>
        <select bind:value={maneuver}>
          <option value="intercept">INTERCEPT</option>
          <option value="match_velocity">MATCH VELOCITY</option>
          <option value="hold">HOLD</option>
          <option value="evasive">EVASIVE</option>
        </select>
      </label>

      {#if rawTier}
        <div class="coord-grid">
          <label class="field"><span>X</span><input type="number" bind:value={position.x} /></label>
          <label class="field"><span>Y</span><input type="number" bind:value={position.y} /></label>
          <label class="field"><span>Z</span><input type="number" bind:value={position.z} /></label>
          <label class="field"><span>VX</span><input type="number" bind:value={velocity.x} /></label>
          <label class="field"><span>VY</span><input type="number" bind:value={velocity.y} /></label>
          <label class="field"><span>VZ</span><input type="number" bind:value={velocity.z} /></label>
        </div>
      {/if}

      <button type="button" on:click={() => sendOrder()}>EXECUTE MANEUVER</button>
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

  .field,
  .proposal-card,
  .feedback,
  .empty {
    display: grid;
    gap: 8px;
  }

  .proposal-card,
  .feedback,
  .empty {
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .simple-grid,
  .coord-grid {
    display: grid;
    gap: 8px;
  }

  .simple-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .coord-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .head,
  .button-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-sm);
    align-items: center;
  }

  .field span,
  .reason,
  .feedback,
  .empty {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong,
  input,
  select,
  button {
    font-family: var(--font-mono);
  }

  strong {
    color: var(--text-primary);
  }

  input,
  select,
  button {
    width: 100%;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    font-size: 0.72rem;
  }

  .button-row button {
    flex: 1;
  }

  .feedback {
    color: var(--status-info);
  }

  @media (max-width: 640px) {
    .simple-grid,
    .coord-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
