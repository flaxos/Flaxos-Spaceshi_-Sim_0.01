<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";

  interface CampaignStatus {
    name?: string;
    description?: string;
    credits?: number;
    reputation?: number;
    completed_missions?: number;
    total_missions?: number;
    next_missions?: Array<{ id: string; name?: string; description?: string; difficulty?: string }>;
    ship_status?: { hull?: number; fuel?: number; systems?: Record<string, unknown> };
    crew?: Array<{ name?: string; station?: string; health?: number }>;
  }

  let campaign: CampaignStatus | null = null;
  let loading = false;
  let gen = 0;
  let newCampaignName = "";
  let saving = false;
  let statusMsg = "";

  async function fetchCampaign() {
    loading = true;
    try {
      const resp = await wsClient.send("campaign_status", {}) as { ok?: boolean; campaign?: CampaignStatus };
      if (resp?.ok !== false) campaign = resp?.campaign ?? null;
    } catch { /* skip */ }
    finally { loading = false; }
  }

  async function loadCampaignMission(missionId: string) {
    try {
      await wsClient.send("campaign_load", { mission: missionId });
      statusMsg = "Mission loaded.";
      setTimeout(() => statusMsg = "", 2000);
    } catch { statusMsg = "Failed to load mission."; }
  }

  async function saveCampaign() {
    saving = true;
    try {
      await wsClient.send("campaign_save", {});
      statusMsg = "Campaign saved.";
      setTimeout(() => statusMsg = "", 2000);
    } catch { statusMsg = "Save failed."; }
    finally { saving = false; }
  }

  async function newCampaign() {
    if (!newCampaignName.trim()) return;
    try {
      await wsClient.send("campaign_new", { name: newCampaignName.trim() });
      newCampaignName = "";
      statusMsg = "Campaign started.";
      fetchCampaign();
    } catch { statusMsg = "Failed to create campaign."; }
  }

  onMount(() => { fetchCampaign(); });
  onDestroy(() => { gen++; });
</script>

<div class="hub-root">
  <div class="hub-header">
    <span class="hub-title">CAMPAIGN HUB</span>
    <button class="btn-icon" title="Save" on:click={saveCampaign} disabled={saving}>
      {saving ? "..." : "💾"}
    </button>
    <button class="btn-icon" title="Refresh" on:click={fetchCampaign} disabled={loading}>⟳</button>
  </div>

  {#if statusMsg}<div class="status-msg">{statusMsg}</div>{/if}

  {#if loading}
    <div class="loading">Loading campaign...</div>
  {:else if !campaign}
    <div class="no-campaign">
      <p>No active campaign.</p>
      <div class="new-campaign-row">
        <input class="campaign-input" type="text" placeholder="Campaign name..." bind:value={newCampaignName} />
        <button class="action-btn" on:click={newCampaign}>NEW CAMPAIGN</button>
      </div>
    </div>
  {:else}
    <!-- Campaign info -->
    {#if campaign.name}
      <div class="campaign-name">{campaign.name}</div>
    {/if}
    {#if campaign.description}
      <div class="campaign-desc">{campaign.description}</div>
    {/if}

    <!-- Stats row -->
    <div class="stats-row">
      {#if campaign.credits !== undefined}
        <div class="stat-item">
          <span class="stat-label">CREDITS</span>
          <span class="stat-value">{campaign.credits.toLocaleString()}</span>
        </div>
      {/if}
      {#if campaign.reputation !== undefined}
        <div class="stat-item">
          <span class="stat-label">REPUTATION</span>
          <span class="stat-value">{campaign.reputation}</span>
        </div>
      {/if}
      {#if campaign.completed_missions !== undefined && campaign.total_missions !== undefined}
        <div class="stat-item">
          <span class="stat-label">MISSIONS</span>
          <span class="stat-value">{campaign.completed_missions}/{campaign.total_missions}</span>
        </div>
      {/if}
    </div>

    <!-- Ship status -->
    {#if campaign.ship_status}
      <div class="section-header">SHIP STATUS</div>
      <div class="ship-status-row">
        {#if campaign.ship_status.hull !== undefined}
          <div class="bar-item">
            <span class="bar-label">HULL</span>
            <div class="bar-track"><div class="bar-fill hull" style="width: {Math.round((campaign.ship_status.hull ?? 0) * 100)}%"></div></div>
            <span class="bar-val">{Math.round((campaign.ship_status.hull ?? 0) * 100)}%</span>
          </div>
        {/if}
        {#if campaign.ship_status.fuel !== undefined}
          <div class="bar-item">
            <span class="bar-label">FUEL</span>
            <div class="bar-track"><div class="bar-fill fuel" style="width: {Math.round((campaign.ship_status.fuel ?? 0) * 100)}%"></div></div>
            <span class="bar-val">{Math.round((campaign.ship_status.fuel ?? 0) * 100)}%</span>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Crew summary -->
    {#if campaign.crew && campaign.crew.length > 0}
      <div class="section-header">CREW</div>
      <div class="crew-list">
        {#each campaign.crew.slice(0, 6) as member}
          <div class="crew-row">
            <span class="crew-name">{member.name ?? "Unknown"}</span>
            <span class="crew-station">{member.station ?? "--"}</span>
            {#if member.health !== undefined}
              <span class="crew-health" class:injured={member.health < 0.75}>{Math.round(member.health * 100)}%</span>
            {/if}
          </div>
        {/each}
        {#if campaign.crew.length > 6}
          <div class="crew-more">+{campaign.crew.length - 6} more</div>
        {/if}
      </div>
    {/if}

    <!-- Next missions -->
    {#if campaign.next_missions && campaign.next_missions.length > 0}
      <div class="section-header">AVAILABLE MISSIONS</div>
      <div class="next-missions">
        {#each campaign.next_missions as nm}
          <div class="next-mission-card">
            <div class="nm-info">
              <span class="nm-name">{nm.name ?? nm.id}</span>
              {#if nm.difficulty}
                <span class="nm-diff diff-{nm.difficulty}">{nm.difficulty.toUpperCase()}</span>
              {/if}
            </div>
            {#if nm.description}
              <div class="nm-desc">{nm.description}</div>
            {/if}
            <button class="action-btn nm-launch" on:click={() => loadCampaignMission(nm.id)}>LOAD</button>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .hub-root {
    padding: var(--space-sm);
    font-family: var(--font-sans);
    color: var(--text-primary);
  }

  .hub-header {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    margin-bottom: var(--space-sm);
  }

  .hub-title {
    flex: 1;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-secondary);
  }

  .btn-icon {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-dim);
    font-size: 0.9rem;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    transition: color var(--transition-fast);
  }
  .btn-icon:hover:not(:disabled) { color: var(--text-primary); }

  .status-msg {
    font-size: var(--font-size-xs);
    color: var(--status-nominal);
    font-family: var(--font-mono);
    margin-bottom: var(--space-xs);
  }

  .loading, .no-campaign {
    text-align: center;
    padding: var(--space-lg);
    color: var(--text-dim);
    font-size: var(--font-size-sm);
  }

  .new-campaign-row {
    display: flex;
    gap: var(--space-xs);
    margin-top: var(--space-sm);
    justify-content: center;
  }

  .campaign-input {
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    padding: 4px 8px;
    width: 160px;
  }

  .campaign-name {
    font-family: var(--font-mono);
    font-size: var(--font-size-base);
    font-weight: 600;
    color: var(--tier-accent, var(--hud-primary));
    margin-bottom: 2px;
  }

  .campaign-desc {
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    margin-bottom: var(--space-sm);
  }

  .stats-row {
    display: flex;
    gap: var(--space-md);
    margin-bottom: var(--space-sm);
    padding: var(--space-xs) var(--space-sm);
    background: var(--bg-input);
    border-radius: var(--radius-sm);
  }

  .stat-item { display: flex; flex-direction: column; }
  .stat-label { font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-dim); text-transform: uppercase; }
  .stat-value { font-family: var(--font-mono); font-size: var(--font-size-sm); font-weight: 600; color: var(--text-primary); }

  .section-header {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: var(--space-sm) 0 var(--space-xs);
    padding-bottom: 4px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .ship-status-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--space-sm); }

  .bar-item { display: flex; align-items: center; gap: var(--space-xs); }
  .bar-label { font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-dim); width: 36px; }
  .bar-track { flex: 1; height: 6px; background: var(--bg-input); border-radius: 3px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
  .bar-fill.hull { background: var(--status-nominal); }
  .bar-fill.fuel { background: var(--status-info); }
  .bar-val { font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-secondary); width: 32px; text-align: right; }

  .crew-list { display: flex; flex-direction: column; gap: 2px; margin-bottom: var(--space-sm); }
  .crew-row { display: flex; gap: var(--space-xs); align-items: center; padding: 3px 0; }
  .crew-name { flex: 1; font-size: var(--font-size-xs); color: var(--text-primary); }
  .crew-station { font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-dim); }
  .crew-health { font-family: var(--font-mono); font-size: 0.6rem; color: var(--status-nominal); }
  .crew-health.injured { color: var(--status-warning); }
  .crew-more { font-size: var(--font-size-xs); color: var(--text-dim); text-align: center; padding: 2px; }

  .next-missions { display: flex; flex-direction: column; gap: var(--space-xs); }

  .next-mission-card {
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: var(--space-xs) var(--space-sm);
  }

  .nm-info { display: flex; align-items: center; gap: var(--space-xs); margin-bottom: 2px; }
  .nm-name { font-size: var(--font-size-xs); font-weight: 600; color: var(--text-primary); flex: 1; }
  .nm-diff { font-family: var(--font-mono); font-size: 0.6rem; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
  .nm-diff.diff-easy { color: var(--status-nominal); background: rgba(0,255,136,0.1); }
  .nm-diff.diff-medium { color: var(--status-warning); background: rgba(255,170,0,0.1); }
  .nm-diff.diff-hard { color: var(--alert-warning); background: rgba(255,102,0,0.1); }
  .nm-diff.diff-extreme { color: var(--status-critical); background: rgba(255,68,68,0.1); }
  .nm-diff.diff-tutorial { color: var(--status-info); background: rgba(0,170,255,0.1); }

  .nm-desc { font-size: 0.65rem; color: var(--text-secondary); margin-bottom: var(--space-xs); line-height: 1.3; }

  .nm-launch {
    font-size: 0.65rem;
    padding: 2px 10px;
  }

  .action-btn {
    background: var(--tier-accent, var(--hud-primary));
    border: none;
    border-radius: var(--radius-sm);
    color: #0a0a0f;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    padding: 4px 12px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: filter var(--transition-fast);
  }
  .action-btn:hover { filter: brightness(1.15); }
  .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
