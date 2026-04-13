<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import type { Proposal } from "../../lib/stores/proposals.js";

  export let proposal: Proposal;
  export let onApprove: (id: string) => void = () => {};
  export let onDeny: (id: string) => void = () => {};

  let timeLeft = proposal.time_remaining ?? (proposal.total_time ?? 30);
  let interval: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    interval = setInterval(() => {
      timeLeft = Math.max(0, timeLeft - 0.1);
    }, 100);
  });

  onDestroy(() => {
    if (interval != null) clearInterval(interval);
  });

  $: totalTime = proposal.total_time ?? 30;
  $: fillPct = totalTime > 0 ? Math.max(0, Math.min(100, (timeLeft / totalTime) * 100)) : 0;
  $: isUrgent = timeLeft < 5 && timeLeft > 0;
  $: confidencePct = Math.round(proposal.confidence * 100);

  function formatTarget(): string {
    return proposal.target_id ?? proposal.target ?? "";
  }
</script>

<div class="proposal-card" class:urgent={isUrgent}>
  <div class="proposal-header">
    <span class="proposal-action">{proposal.action || "—"}</span>
    {#if confidencePct > 0}
      <span class="proposal-confidence">{confidencePct}%</span>
    {/if}
    {#if proposal.crew_efficiency != null}
      <span class="proposal-crew">Crew: {Math.round(proposal.crew_efficiency * 100)}%</span>
    {/if}
    <span class="proposal-countdown" class:expiring={timeLeft < 10}>{timeLeft.toFixed(1)}s</span>
  </div>

  {#if formatTarget()}
    <div class="proposal-target">TGT: {formatTarget()}</div>
  {/if}

  {#if proposal.reason}
    <div class="proposal-reason">{proposal.reason}</div>
  {/if}

  {#if proposal.auto_execute}
    <div class="proposal-auto">Auto-execute in {Math.ceil(timeLeft)}s</div>
  {/if}

  <div class="proposal-timer">
    <div class="proposal-timer-fill" style="width: {fillPct}%;"></div>
  </div>

  <div class="proposal-actions">
    <button class="proposal-approve" type="button" on:click={() => onApprove(proposal.id)}>
      APPROVE
    </button>
    <button class="proposal-deny" type="button" on:click={() => onDeny(proposal.id)}>
      DENY
    </button>
  </div>
</div>

<style>
  .proposal-card {
    display: grid;
    gap: 6px;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(192, 160, 255, 0.25);
    background: rgba(192, 160, 255, 0.05);
    animation: proposalSlideIn 0.2s ease-out;
  }

  .proposal-card.urgent {
    border-color: rgba(255, 170, 0, 0.5);
    background: rgba(255, 170, 0, 0.07);
    animation: proposalPulse 1s ease-in-out infinite;
  }

  .proposal-header {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .proposal-action {
    flex: 1;
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    color: var(--text-primary);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .proposal-confidence {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: rgba(192, 160, 255, 0.9);
    font-weight: 600;
  }

  .proposal-crew {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  .proposal-countdown {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    min-width: 36px;
    text-align: right;
  }

  .proposal-countdown.expiring {
    color: rgba(255, 170, 0, 0.9);
  }

  .proposal-card.urgent .proposal-countdown {
    color: #ffaa00;
    font-weight: 600;
  }

  .proposal-target,
  .proposal-auto {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .proposal-reason {
    font-size: var(--font-size-xs);
    color: var(--text-dim, var(--text-secondary));
    font-style: italic;
  }

  .proposal-timer {
    height: 3px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    overflow: hidden;
  }

  .proposal-timer-fill {
    height: 100%;
    background: rgba(192, 160, 255, 0.7);
    transition: width 0.1s linear;
  }

  .proposal-card.urgent .proposal-timer-fill {
    background: rgba(255, 170, 0, 0.8);
  }

  .proposal-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-sm);
  }

  .proposal-approve,
  .proposal-deny {
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    cursor: pointer;
    letter-spacing: 0.05em;
    transition: background 0.1s, border-color 0.1s;
  }

  .proposal-approve {
    border-color: rgba(0, 255, 136, 0.4);
    background: rgba(0, 255, 136, 0.08);
    color: rgba(0, 255, 136, 0.9);
  }

  .proposal-approve:hover {
    background: rgba(0, 255, 136, 0.18);
    border-color: rgba(0, 255, 136, 0.7);
  }

  .proposal-deny {
    border-color: rgba(255, 68, 68, 0.35);
    background: rgba(255, 68, 68, 0.07);
    color: rgba(255, 100, 100, 0.9);
  }

  .proposal-deny:hover {
    background: rgba(255, 68, 68, 0.16);
    border-color: rgba(255, 68, 68, 0.6);
  }

  @keyframes proposalSlideIn {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  @keyframes proposalPulse {
    0%, 100% { border-color: rgba(255, 170, 0, 0.5); }
    50%       { border-color: rgba(255, 170, 0, 0.9); }
  }

  @media (prefers-reduced-motion: reduce) {
    .proposal-card,
    .proposal-card.urgent {
      animation: none;
    }
  }
</style>
