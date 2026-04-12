<script lang="ts">
  import { onMount } from "svelte";
  import Panel from "../layout/Panel.svelte";
  import { tier } from "../../lib/stores/tier.js";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    formatChoiceCountdown,
    normalizeCommsChoices,
    recommendChoice,
    type CommsChoice,
  } from "./commsData.js";

  let choices: CommsChoice[] = [];
  let feedback = "";
  let nowSeconds = Date.now() / 1000;
  let pollHandle: number | null = null;
  let timerHandle: number | null = null;

  $: cpuAssistTier = $tier === "cpu-assist";

  onMount(() => {
    void refresh();
    pollHandle = window.setInterval(() => void refresh(), 2000);
    timerHandle = window.setInterval(() => {
      nowSeconds = Date.now() / 1000;
    }, 250);
    return () => {
      if (pollHandle != null) window.clearInterval(pollHandle);
      if (timerHandle != null) window.clearInterval(timerHandle);
    };
  });

  async function refresh() {
    try {
      const response = await wsClient.sendShipCommand("get_comms_choices", {});
      choices = normalizeCommsChoices(response);
    } catch {
      choices = [];
    }
  }

  async function respond(choice: CommsChoice, optionId: string) {
    feedback = "";
    try {
      await wsClient.sendShipCommand("comms_respond", {
        choice_id: choice.choiceId,
        option_id: optionId,
      });
      feedback = "Response transmitted";
      await refresh();
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Response failed";
    }
  }
</script>

<Panel title="Incoming Traffic" domain="comms" priority="primary" className="comms-choice-panel">
  <div class="shell">
    {#if choices.length === 0}
      <div class="empty">No active comms choices.</div>
    {:else}
      {#each choices as choice}
        {@const countdown = formatChoiceCountdown(choice, nowSeconds)}
        {@const recommended = recommendChoice(choice)}
        <section class="choice-card">
          <div class="choice-head">
            <strong>{choice.contactId.toUpperCase()}</strong>
            {#if choice.timeout != null}
              <span>{Math.ceil(countdown.remaining)}s</span>
            {:else}
              <span>OPEN</span>
            {/if}
          </div>

          <div class="prompt">{choice.prompt}</div>

          {#if choice.timeout != null}
            <div class="track">
              <div class="fill" style={`width:${(countdown.progress * 100).toFixed(1)}%;`}></div>
            </div>
          {/if}

          <div class="options">
            {#each choice.options as option}
              <button
                type="button"
                class:recommended={cpuAssistTier && recommended?.optionId === option.optionId}
                on:click={() => respond(choice, option.optionId)}
              >
                <strong>{option.label}</strong>
                {#if option.description}
                  <span>{option.description}</span>
                {/if}
                {#if cpuAssistTier && recommended?.optionId === option.optionId}
                  <em>Recommended</em>
                {/if}
              </button>
            {/each}
          </div>
        </section>
      {/each}
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

  .choice-card,
  .feedback,
  .empty {
    display: grid;
    gap: 10px;
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(255, 255, 255, 0.02);
  }

  .choice-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
  }

  .prompt,
  .feedback,
  .empty,
  .options span,
  .options em {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
  }

  strong {
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .track {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(0, 255, 136, 0.85), rgba(255, 68, 68, 0.85));
    transform-origin: left center;
  }

  .options {
    display: grid;
    gap: 8px;
  }

  .options button {
    display: grid;
    gap: 6px;
    text-align: left;
    width: 100%;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    font-family: inherit;
  }

  .options button.recommended {
    border-color: rgba(var(--tier-accent-rgb), 0.45);
    background: rgba(var(--tier-accent-rgb), 0.12);
  }

  .options em {
    color: var(--status-info);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-style: normal;
  }

  .feedback {
    color: var(--status-info);
  }
</style>
