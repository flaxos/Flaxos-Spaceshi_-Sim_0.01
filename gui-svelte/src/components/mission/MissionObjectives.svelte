<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  interface Objective {
    id?: string;
    description?: string;
    status?: "pending" | "completed" | "failed";
    required?: boolean;
    type?: string;
    progress?: string | number;
  }

  interface Mission {
    name?: string;
    description?: string;
    briefing?: string;
    mission_status?: string;
    status?: string;
    objectives?: Objective[] | Record<string, Objective>;
    time_remaining?: number;
    time_elapsed?: number;
    time_limit?: number;
    hints?: Array<{ message?: string } | string>;
    success_message?: string;
    failure_message?: string;
    next_scenario?: string;
    available?: boolean;
  }

  let mission: Mission | null = null;
  let gen = 0;

  function formatSeconds(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  function formatTime(m: Mission): string {
    if (typeof m.time_remaining === "number" && m.time_remaining > 0) {
      return `${formatSeconds(m.time_remaining)} remaining`;
    }
    if (typeof m.time_elapsed === "number") {
      const elapsed = formatSeconds(m.time_elapsed);
      if (typeof m.time_limit === "number") return `${elapsed} / ${formatSeconds(m.time_limit)}`;
      return elapsed;
    }
    return "--:--";
  }

  function getObjectives(m: Mission): Objective[] {
    if (!m.objectives) return [];
    if (Array.isArray(m.objectives)) return m.objectives;
    return Object.entries(m.objectives).map(([id, obj]) => ({ id, ...obj }));
  }

  async function poll(g: number) {
    if (g !== gen) return;
    try {
      const resp = await wsClient.send("get_mission", {}) as { ok?: boolean; mission?: Mission } & Mission;
      if (g !== gen) return;
      if (resp?.ok !== false) {
        mission = resp?.mission ?? (resp?.name ? resp : null);
      }
    } catch { /* skip */ }
    if (g === gen) setTimeout(() => poll(g), 2000);
  }

  let scenarioHandler: ((e: Event) => void) | null = null;

  onMount(() => {
    gen++;
    poll(gen);

    scenarioHandler = (e: Event) => {
      const detail = (e as CustomEvent<{ mission?: Mission }>).detail;
      if (detail?.mission) mission = detail.mission;
      else { gen++; poll(gen); }
    };
    document.addEventListener("scenario-loaded", scenarioHandler);
  });

  onDestroy(() => {
    gen++;
    if (scenarioHandler) document.removeEventListener("scenario-loaded", scenarioHandler);
  });

  $: status = mission?.mission_status ?? mission?.status ?? "in_progress";
  $: objectives = mission ? getObjectives(mission) : [];
  $: hints = (mission?.hints ?? []) as Array<{ message?: string } | string>;
</script>

<div class="objectives-root">
  {#if !mission || mission.available === false}
    <div class="no-mission">No mission loaded</div>
  {:else}
    <div class="mission-header">
      <div class="mission-name">{mission.name ?? "Mission"}</div>
      {#if mission.description || mission.briefing}
        <div class="mission-desc">{mission.description ?? mission.briefing}</div>
      {/if}
    </div>

    <div class="status-row">
      <div class="status-indicator">
        <span class="status-dot" class:in-progress={status === "in_progress"} class:success={status === "success"} class:failure={status === "failure"}></span>
        <span class="status-text {status.replace('_', '-')}">{status.replace("_", " ").toUpperCase()}</span>
      </div>
      <div class="time-display">{formatTime(mission)}</div>
    </div>

    {#if objectives.length > 0}
      <div class="objectives-list">
        {#each objectives as obj}
          {@const objStatus = obj.status ?? "pending"}
          {@const isRequired = obj.required !== false}
          <div class="objective" class:completed={objStatus === "completed"} class:failed={objStatus === "failed"} class:required={isRequired}>
            <div class="obj-header">
              <span class="obj-check" class:completed={objStatus === "completed"} class:failed={objStatus === "failed"}>
                {objStatus === "completed" ? "☑" : objStatus === "failed" ? "☒" : "☐"}
              </span>
              <span class="obj-text">{obj.description ?? obj.id ?? ""}</span>
              {#if !isRequired}<span class="optional-tag">Optional</span>{/if}
            </div>
            {#if obj.type || obj.progress}
              <div class="obj-meta">
                {#if obj.type}Type: {obj.type}{/if}
                {#if obj.progress} • Progress: {obj.progress}{/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    {#if hints.length > 0}
      <div class="hints-section">
        <div class="hints-title">HINTS</div>
        {#each hints as hint}
          <div class="hint">{typeof hint === "string" ? hint : hint.message ?? ""}</div>
        {/each}
      </div>
    {/if}

    {#if status === "success"}
      <div class="result-box success">
        <div class="result-title">✓ MISSION COMPLETE</div>
        <div class="result-text">{mission.success_message ?? "All objectives achieved."}</div>
      </div>
    {:else if status === "failure"}
      <div class="result-box failure">
        <div class="result-title">✕ MISSION FAILED</div>
        <div class="result-text">{mission.failure_message ?? "Mission objectives not met."}</div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .objectives-root {
    padding: var(--space-sm);
    font-family: var(--font-sans);
    color: var(--text-primary);
  }

  .no-mission {
    text-align: center;
    padding: var(--space-xl);
    color: var(--text-dim);
    font-style: italic;
  }

  .mission-header { margin-bottom: var(--space-sm); }

  .mission-name {
    font-size: var(--font-size-base);
    font-weight: 600;
    color: var(--text-primary);
  }

  .mission-desc {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    margin-top: 2px;
  }

  .status-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-xs) var(--space-sm);
    background: var(--bg-input);
    border-radius: var(--radius-sm);
    margin-bottom: var(--space-sm);
  }

  .status-indicator { display: flex; align-items: center; gap: 8px; }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--border-default);
  }

  .status-dot.in-progress {
    background: var(--status-info);
    box-shadow: 0 0 8px var(--status-info);
    animation: pulse 1.5s ease-in-out infinite;
  }

  .status-dot.success { background: var(--status-nominal); box-shadow: 0 0 8px var(--status-nominal); }
  .status-dot.failure { background: var(--status-critical); box-shadow: 0 0 8px var(--status-critical); }

  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

  .status-text { font-family: var(--font-mono); font-size: var(--font-size-xs); font-weight: 600; color: var(--text-secondary); }
  .status-text.in-progress { color: var(--status-info); }
  .status-text.success { color: var(--status-nominal); }
  .status-text.failure { color: var(--status-critical); }

  .time-display { font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--text-secondary); }

  .objectives-list { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-sm); }

  .objective {
    padding: var(--space-xs) var(--space-sm);
    background: var(--bg-input);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--border-default);
  }

  .objective.required { border-left-color: var(--status-info); }
  .objective.completed { border-left-color: var(--status-nominal); opacity: 0.7; }
  .objective.failed { border-left-color: var(--status-critical); opacity: 0.7; }

  .obj-header { display: flex; align-items: center; gap: var(--space-xs); }

  .obj-check { font-size: 0.9rem; }
  .obj-check.completed { color: var(--status-nominal); }
  .obj-check.failed { color: var(--status-critical); }

  .obj-text { flex: 1; font-size: var(--font-size-xs); color: var(--text-primary); }
  .objective.completed .obj-text { text-decoration: line-through; }

  .optional-tag {
    font-size: 0.6rem;
    padding: 2px 6px;
    background: rgba(255, 170, 0, 0.15);
    color: var(--status-warning);
    border-radius: 3px;
  }

  .obj-meta { font-size: 0.65rem; color: var(--text-dim); margin-top: 2px; }

  .hints-section {
    margin-top: var(--space-sm);
    padding-top: var(--space-xs);
    border-top: 1px solid var(--border-subtle);
  }

  .hints-title {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: var(--space-xs);
  }

  .hint {
    padding: 6px var(--space-sm);
    background: rgba(255, 170, 0, 0.08);
    border-left: 3px solid var(--status-warning);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: var(--font-size-xs);
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .result-box {
    margin-top: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-sm);
    text-align: center;
  }

  .result-box.success { background: rgba(0, 255, 136, 0.08); border: 1px solid var(--status-nominal); }
  .result-box.failure { background: rgba(255, 68, 68, 0.08); border: 1px solid var(--status-critical); }

  .result-title {
    font-size: var(--font-size-base);
    font-weight: 600;
    margin-bottom: 4px;
  }

  .result-box.success .result-title { color: var(--status-nominal); }
  .result-box.failure .result-title { color: var(--status-critical); }

  .result-text { font-size: var(--font-size-xs); color: var(--text-secondary); }
</style>
