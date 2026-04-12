<script lang="ts">
  import { gameState } from "../../lib/stores/gameState.js";
  import { tier } from "../../lib/stores/tier.js";
  import { deriveWorkflowStep, extractShipState } from "./helmData.js";

  const STEPS = {
    manual: ["PLAN", "ORIENT", "BURN", "CHECK"],
    raw: ["PLAN", "ORIENT", "BURN", "CHECK"],
    arcade: ["SENSE", "AIM", "FIRE"],
    "cpu-assist": ["ASSESS", "ORDER", "QUEUE", "MONITOR"],
  } as const;

  $: ship = extractShipState($gameState);
  $: steps = STEPS[$tier];
  $: currentStep = deriveWorkflowStep(ship, $tier);
</script>

<div class="workflow-strip" aria-label="Helm workflow">
  {#each steps as step, index}
    <div class:done={index < currentStep} class:current={index === currentStep} class="step">
      <span class="index">{index + 1}</span>
      <span>{step}</span>
    </div>
    {#if index < steps.length - 1}
      <div class="connector"></div>
    {/if}
  {/each}
</div>

<style>
  .workflow-strip {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    width: 100%;
    min-height: 42px;
    padding: 6px 10px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background:
      linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.08), transparent 45%),
      var(--bg-panel);
    overflow-x: auto;
  }

  .step {
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
    padding: 6px 10px;
    border-radius: 999px;
    color: var(--text-dim);
    border: 1px solid transparent;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .step.done {
    color: var(--status-nominal);
  }

  .step.current {
    color: var(--text-primary);
    border-color: rgba(var(--tier-accent-rgb), 0.4);
    background: rgba(var(--tier-accent-rgb), 0.12);
    box-shadow: var(--glow-tier);
  }

  .index {
    width: 18px;
    height: 18px;
    display: inline-grid;
    place-items: center;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.06);
    font-size: 0.62rem;
  }

  .connector {
    flex: 1 0 22px;
    max-width: 48px;
    height: 1px;
    background: linear-gradient(90deg, rgba(var(--tier-accent-rgb), 0.4), transparent);
  }
</style>
