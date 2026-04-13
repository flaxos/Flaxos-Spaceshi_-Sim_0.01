<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { wsClient } from "../../lib/ws/wsClient.js";
  import {
    describeCommandFailure,
    isCommandRejected,
  } from "../../lib/ws/commandResponse.js";

  type MissionStatus = {
    available?: boolean;
    mission_status?: string;
    status?: string;
    description?: string;
    briefing?: string;
  };

  type ClientSession = {
    ship?: string | null;
    station?: string | null;
    name?: string | null;
  };

  type ServerStatus = {
    ok?: boolean;
    scenario?: string | null;
    mission?: MissionStatus;
    paused?: boolean;
    time_scale?: number;
    tick?: number;
    sim_time?: number;
    ship_count?: number;
    client_count?: number;
    server_uptime?: number;
    mission_uptime?: number | null;
    rcon_session_count?: number;
    clients?: Record<string, ClientSession>;
  };

  type BannerTone = "info" | "success" | "error";

  let authenticated = wsClient.hasRconAuth();
  let authPassword = "";
  let status: ServerStatus | null = null;
  let busyAction: string | null = null;
  let bannerText = authenticated
    ? "RCON session detected. Refreshing server status."
    : "Authenticate with the server RCON password to enable admin controls.";
  let bannerTone: BannerTone = "info";
  let rotateCurrentPassword = "";
  let rotateNewPassword = "";
  let rotateConfirmPassword = "";
  let customTimeScale = "1";
  let lastRefreshedAt: Date | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let clientEntries: Array<[string, ClientSession]> = [];
  let missionStatusText = "idle";

  $: clientEntries = Object.entries(status?.clients ?? {});
  $: missionStatusText = (
    status?.mission?.mission_status
    ?? status?.mission?.status
    ?? (status?.scenario ? "loaded" : "idle")
  ).toString();

  function setBanner(text: string, tone: BannerTone = "info") {
    bannerText = text;
    bannerTone = tone;
  }

  function formatDuration(seconds: number | null | undefined): string {
    if (seconds == null || !Number.isFinite(seconds)) return "n/a";
    const total = Math.max(0, Math.round(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
    if (minutes > 0) return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
    return `${secs}s`;
  }

  function formatNumber(value: number | null | undefined, digits = 0): string {
    if (value == null || !Number.isFinite(value)) return "n/a";
    return value.toFixed(digits);
  }

  function syncAuthState() {
    authenticated = wsClient.hasRconAuth();
    if (!authenticated) status = null;
  }

  function clearLocalSession(message = "RCON session cleared in this browser.") {
    wsClient.clearRconAuth();
    authenticated = false;
    status = null;
    authPassword = "";
    setBanner(message, "info");
  }

  async function refreshStatus(silent = false): Promise<boolean> {
    if (!authenticated) return false;
    if (!silent) busyAction = "refresh";
    try {
      const response = await wsClient.rcon("rcon_status") as ServerStatus;
      syncAuthState();
      if (isCommandRejected(response)) {
        const message = describeCommandFailure(response, "Unable to fetch server status");
        if (!silent || !authenticated) setBanner(message, "error");
        return false;
      }
      status = response;
      customTimeScale = String(response.time_scale ?? 1);
      lastRefreshedAt = new Date();
      if (!silent) setBanner("Server status refreshed.", "success");
      return true;
    } catch (error) {
      if (!silent) {
        setBanner(
          error instanceof Error ? error.message : "Unable to fetch server status",
          "error",
        );
      }
      return false;
    } finally {
      if (!silent) busyAction = null;
    }
  }

  async function authenticate() {
    if (!authPassword) {
      setBanner("Enter the RCON password to continue.", "error");
      return;
    }
    busyAction = "auth";
    try {
      const response = await wsClient.rconAuth(authPassword) as { ok?: boolean; error?: string };
      if (response?.ok) {
        authPassword = "";
        authenticated = true;
        setBanner("RCON authenticated. Admin controls unlocked.", "success");
        await refreshStatus(true);
        return;
      }
      setBanner(describeCommandFailure(response, "RCON authentication failed"), "error");
    } catch (error) {
      setBanner(
        error instanceof Error ? error.message : "RCON authentication failed",
        "error",
      );
    } finally {
      busyAction = null;
    }
  }

  async function runAdminCommand(
    cmd: string,
    args: Record<string, unknown>,
    successMessage: string,
  ): Promise<boolean> {
    busyAction = cmd;
    try {
      const response = await wsClient.rcon(cmd, args);
      syncAuthState();
      if (isCommandRejected(response)) {
        setBanner(describeCommandFailure(response, `${cmd} failed`), "error");
        return false;
      }
      setBanner(successMessage, "success");
      await refreshStatus(true);
      return true;
    } catch (error) {
      setBanner(error instanceof Error ? error.message : `${cmd} failed`, "error");
      return false;
    } finally {
      busyAction = null;
    }
  }

  async function togglePause() {
    const shouldPause = !(status?.paused ?? false);
    await runAdminCommand(
      "rcon_pause",
      { on: shouldPause },
      shouldPause ? "Simulation paused." : "Simulation resumed.",
    );
  }

  async function applyTimeScale(scale: number) {
    customTimeScale = String(scale);
    await runAdminCommand(
      "rcon_timescale",
      { scale },
      `Time scale set to ${scale}x.`,
    );
  }

  async function submitCustomTimeScale() {
    const scale = Number(customTimeScale);
    if (!Number.isFinite(scale)) {
      setBanner("Enter a valid numeric time scale.", "error");
      return;
    }
    await applyTimeScale(scale);
  }

  async function reloadMission() {
    if (!status?.scenario) {
      setBanner("No active scenario is loaded.", "error");
      return;
    }
    if (!window.confirm("Reload the current mission from its initial state?")) return;
    await runAdminCommand("rcon_reload", {}, "Mission reset complete.");
  }

  async function restartServer() {
    if (!window.confirm("Reset the live simulation state? Connected crew will need to re-sync.")) return;
    await runAdminCommand("rcon_restart", {}, "Server reset complete.");
  }

  async function kickClient(clientId: string) {
    if (!window.confirm(`Disconnect client ${clientId}?`)) return;
    await runAdminCommand(
      "rcon_kick",
      { client_id: clientId },
      `Client ${clientId} disconnected.`,
    );
  }

  async function rotatePassword() {
    if (!rotateCurrentPassword || !rotateNewPassword || !rotateConfirmPassword) {
      setBanner("Current password, new password, and confirmation are required.", "error");
      return;
    }
    if (rotateNewPassword !== rotateConfirmPassword) {
      setBanner("New password and confirmation do not match.", "error");
      return;
    }
    if (rotateNewPassword.length < 8) {
      setBanner("New password must be at least 8 characters.", "error");
      return;
    }

    busyAction = "rcon_set_password";
    try {
      const response = await wsClient.rcon("rcon_set_password", {
        current_password: rotateCurrentPassword,
        new_password: rotateNewPassword,
      });
      syncAuthState();
      if (isCommandRejected(response)) {
        setBanner(
          describeCommandFailure(response, "Unable to rotate the RCON password"),
          "error",
        );
        return;
      }

      rotateCurrentPassword = "";
      rotateNewPassword = "";
      rotateConfirmPassword = "";
      clearLocalSession(
        "RCON password updated for this server process. Re-authenticate with the new password to continue.",
      );
      bannerTone = "success";
    } catch (error) {
      setBanner(
        error instanceof Error ? error.message : "Unable to rotate the RCON password",
        "error",
      );
    } finally {
      busyAction = null;
    }
  }

  onMount(() => {
    if (authenticated) {
      refreshStatus(true);
    }
    pollTimer = setInterval(() => {
      if (authenticated) {
        void refreshStatus(true);
      }
    }, 5000);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });
</script>

<div class="admin-root">
  <div class="hero">
    <div>
      <h3>Server Control</h3>
      <p>RCON-backed controls for UAT, mission resets, and live session triage.</p>
    </div>
    {#if authenticated}
      <div class="hero-actions">
        <button
          type="button"
          disabled={busyAction !== null}
          on:click={() => refreshStatus(false)}
        >Refresh</button>
        <button
          type="button"
          class="secondary"
          disabled={busyAction !== null}
          on:click={() => clearLocalSession()}
        >Clear Session</button>
      </div>
    {/if}
  </div>

  <div class={`banner ${bannerTone}`}>{bannerText}</div>

  {#if !authenticated}
    <section class="card auth-card">
      <div class="section-head">
        <div>
          <h4>Authenticate</h4>
          <p>Credentials stay in memory only. Nothing is written to browser storage.</p>
        </div>
      </div>
      <div class="auth-row">
        <input
          type="password"
          bind:value={authPassword}
          autocomplete="current-password"
          placeholder="RCON password"
          on:keydown={(event) => event.key === "Enter" && authenticate()}
        />
        <button type="button" disabled={busyAction !== null} on:click={authenticate}>
          Unlock
        </button>
      </div>
    </section>
  {:else}
    <div class="stats-grid">
      <article class="card stat-card">
        <span class="stat-label">Server Uptime</span>
        <strong>{formatDuration(status?.server_uptime)}</strong>
        <small>{status?.paused ? "Simulation paused" : "Simulation running"}</small>
      </article>
      <article class="card stat-card">
        <span class="stat-label">Mission Uptime</span>
        <strong>{formatDuration(status?.mission_uptime)}</strong>
        <small>{status?.scenario ?? "No scenario loaded"}</small>
      </article>
      <article class="card stat-card">
        <span class="stat-label">Mission State</span>
        <strong>{missionStatusText}</strong>
        <small>{status?.mission?.description ?? status?.mission?.briefing ?? "Awaiting status payload"}</small>
      </article>
      <article class="card stat-card">
        <span class="stat-label">Crew Sessions</span>
        <strong>{status?.client_count ?? 0}</strong>
        <small>{status?.ship_count ?? 0} ships · {status?.rcon_session_count ?? 0} admin session(s)</small>
      </article>
      <article class="card stat-card">
        <span class="stat-label">Sim Clock</span>
        <strong>{formatNumber(status?.sim_time, 1)} s</strong>
        <small>Tick {formatNumber(status?.tick, 0)} · {formatNumber(status?.time_scale, 1)}x time scale</small>
      </article>
      <article class="card stat-card">
        <span class="stat-label">Last Refresh</span>
        <strong>{lastRefreshedAt ? lastRefreshedAt.toLocaleTimeString() : "Pending"}</strong>
        <small>Auto-refresh every 5 seconds while authenticated</small>
      </article>
    </div>

    <div class="section-grid">
      <section class="card">
        <div class="section-head">
          <div>
            <h4>Mission Controls</h4>
            <p>Use explicit reset paths rather than reloading the page during UAT.</p>
          </div>
        </div>
        <div class="button-grid">
          <button type="button" disabled={busyAction !== null} on:click={togglePause}>
            {status?.paused ? "Resume Simulation" : "Pause Simulation"}
          </button>
          <button type="button" disabled={busyAction !== null} on:click={reloadMission}>
            Reset Mission
          </button>
          <button type="button" class="danger" disabled={busyAction !== null} on:click={restartServer}>
            Reset Server
          </button>
        </div>
      </section>

      <section class="card">
        <div class="section-head">
          <div>
            <h4>Time Scale</h4>
            <p>Useful for scripted UAT passes, paused inspection, and faster setup loops.</p>
          </div>
        </div>
        <div class="button-grid compact">
          <button type="button" disabled={busyAction !== null} on:click={() => applyTimeScale(0.5)}>0.5x</button>
          <button type="button" disabled={busyAction !== null} on:click={() => applyTimeScale(1)}>1x</button>
          <button type="button" disabled={busyAction !== null} on:click={() => applyTimeScale(2)}>2x</button>
          <button type="button" disabled={busyAction !== null} on:click={() => applyTimeScale(5)}>5x</button>
        </div>
        <div class="inline-form">
          <input
            type="number"
            min="0.1"
            max="10"
            step="0.1"
            bind:value={customTimeScale}
            placeholder="Custom scale"
            on:keydown={(event) => event.key === "Enter" && submitCustomTimeScale()}
          />
          <button type="button" disabled={busyAction !== null} on:click={submitCustomTimeScale}>
            Apply
          </button>
        </div>
      </section>

      <section class="card">
        <div class="section-head">
          <div>
            <h4>Rotate RCON Password</h4>
            <p>Runtime only. Update your launch environment separately if the new password should survive a restart.</p>
          </div>
        </div>
        <div class="stacked-fields">
          <input
            type="password"
            bind:value={rotateCurrentPassword}
            autocomplete="current-password"
            placeholder="Current password"
          />
          <input
            type="password"
            bind:value={rotateNewPassword}
            autocomplete="new-password"
            placeholder="New password"
          />
          <input
            type="password"
            bind:value={rotateConfirmPassword}
            autocomplete="new-password"
            placeholder="Confirm new password"
            on:keydown={(event) => event.key === "Enter" && rotatePassword()}
          />
        </div>
        <button type="button" class="secondary" disabled={busyAction !== null} on:click={rotatePassword}>
          Update Password
        </button>
      </section>
    </div>

    <section class="card">
      <div class="section-head">
        <div>
          <h4>Connected Clients</h4>
          <p>Kick stale or misbehaving sessions without restarting the whole sim.</p>
        </div>
      </div>
      {#if clientEntries.length === 0}
        <div class="empty-state">No connected station sessions.</div>
      {:else}
        <div class="client-list">
          {#each clientEntries as [clientId, client]}
            <div class="client-row">
              <div class="client-meta">
                <strong>{client.name || clientId}</strong>
                <span>{clientId}</span>
              </div>
              <div class="client-state">
                <span>{client.ship || "Unassigned ship"}</span>
                <span>{client.station || "No station claimed"}</span>
              </div>
              <button
                type="button"
                class="danger ghost"
                disabled={busyAction !== null}
                on:click={() => kickClient(clientId)}
              >Kick</button>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .admin-root {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
    height: 100%;
    overflow-y: auto;
    padding: var(--space-xs);
  }

  .hero,
  .section-head,
  .auth-row,
  .inline-form,
  .client-row,
  .client-meta,
  .client-state,
  .hero-actions {
    display: flex;
    align-items: center;
  }

  .hero,
  .section-head,
  .client-row {
    justify-content: space-between;
  }

  .hero {
    gap: var(--space-sm);
    flex-wrap: wrap;
  }

  h3,
  h4,
  p {
    margin: 0;
  }

  .hero h3,
  .section-head h4 {
    font-family: var(--font-sans);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .hero p,
  .section-head p,
  .stat-card small,
  .client-meta span,
  .client-state span,
  .empty-state {
    color: var(--text-secondary);
  }

  .banner {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    font-size: var(--font-size-xs);
    background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  }

  .banner.info {
    border-color: color-mix(in srgb, var(--hud-primary) 30%, var(--border-default));
  }

  .banner.success {
    border-color: color-mix(in srgb, var(--status-nominal) 55%, var(--border-default));
    color: var(--text-primary);
  }

  .banner.error {
    border-color: color-mix(in srgb, var(--status-critical) 60%, var(--border-default));
    color: var(--status-critical);
  }

  .card {
    background: color-mix(in srgb, var(--bg-panel) 92%, transparent);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-sm);
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .stats-grid,
  .section-grid,
  .button-grid {
    display: grid;
    gap: var(--space-sm);
  }

  .stats-grid {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .section-grid {
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }

  .stat-card strong {
    font-size: 1.35rem;
    font-family: var(--font-sans);
    font-weight: 700;
    color: var(--text-primary);
  }

  .stat-label {
    color: var(--tier-accent, var(--hud-primary));
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.7rem;
  }

  .button-grid {
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  }

  .button-grid.compact {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .auth-row,
  .inline-form,
  .stacked-fields,
  .hero-actions,
  .client-meta,
  .client-state {
    gap: var(--space-xs);
  }

  .stacked-fields {
    display: flex;
    flex-direction: column;
  }

  input,
  button {
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
  }

  input {
    width: 100%;
    background: var(--bg-input);
    color: var(--text-primary);
    padding: 10px 12px;
  }

  button {
    padding: 10px 12px;
    background: color-mix(in srgb, var(--tier-accent, var(--hud-primary)) 22%, var(--bg-panel));
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast), border-color var(--transition-fast), opacity var(--transition-fast);
  }

  button:hover:not(:disabled) {
    background: color-mix(in srgb, var(--tier-accent, var(--hud-primary)) 34%, var(--bg-panel));
  }

  button.secondary {
    background: var(--bg-panel);
  }

  button.danger {
    border-color: color-mix(in srgb, var(--status-critical) 55%, var(--border-default));
    color: var(--status-critical);
  }

  button.ghost {
    background: transparent;
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .client-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .client-row {
    gap: var(--space-sm);
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--bg-void) 72%, transparent);
    border: 1px solid color-mix(in srgb, var(--border-default) 70%, transparent);
    flex-wrap: wrap;
  }

  .client-meta,
  .client-state {
    flex-direction: column;
    align-items: flex-start;
    min-width: 0;
  }

  .client-meta strong,
  .client-state span:first-child {
    color: var(--text-primary);
  }

  .empty-state {
    padding: var(--space-xs) 0;
    font-style: italic;
  }

  @media (max-width: 900px) {
    .button-grid.compact {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 720px) {
    .hero-actions,
    .auth-row,
    .inline-form,
    .client-row {
      flex-direction: column;
      align-items: stretch;
    }

    .hero-actions,
    .auth-row,
    .inline-form {
      width: 100%;
    }

    .section-head {
      align-items: flex-start;
    }

    .button-grid,
    .button-grid.compact,
    .stats-grid,
    .section-grid {
      grid-template-columns: 1fr;
    }

    .client-row button {
      width: 100%;
    }
  }
</style>
