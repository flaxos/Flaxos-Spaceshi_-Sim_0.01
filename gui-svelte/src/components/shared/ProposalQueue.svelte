<script lang="ts">
  import ProposalCard from "./ProposalCard.svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import type { Proposal, StationKey } from "../../lib/stores/proposals.js";

  export let proposals: Proposal[] = [];
  export let station: StationKey;

  async function approve(id: string) {
    await wsClient.sendShipCommand(`approve_${station}`, { proposal_id: id });
  }

  async function deny(id: string) {
    await wsClient.sendShipCommand(`deny_${station}`, { proposal_id: id });
  }
</script>

<div class="proposal-queue">
  {#if proposals.length === 0}
    <div class="no-proposals">No pending proposals — system idle</div>
  {:else}
    {#each proposals as proposal (proposal.id)}
      <ProposalCard {proposal} onApprove={approve} onDeny={deny} />
    {/each}
  {/if}
</div>

<style>
  .proposal-queue {
    display: grid;
    gap: var(--space-sm);
  }

  .no-proposals {
    padding: 12px 10px;
    font-size: var(--font-size-xs);
    color: var(--text-dim, var(--text-secondary));
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border: 1px dashed rgba(192, 160, 255, 0.15);
    border-radius: var(--radius-sm);
  }
</style>
