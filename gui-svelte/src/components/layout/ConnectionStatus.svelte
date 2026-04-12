<script lang="ts">
  import { connection } from "../../lib/stores/connection.js";
  import { wsClient } from "../../lib/ws/wsClient.js";

  function reconnect() {
    wsClient.connect().catch(() => {});
  }
</script>

<button
  class="conn-pill"
  class:connected={$connection.status === "connected"}
  class:connecting={$connection.status === "connecting"}
  class:disconnected={$connection.status === "disconnected"}
  on:click={reconnect}
  title="{$connection.status === 'connected' ? 'Connected' : 'Click to reconnect'}{$connection.latency !== null ? ` · ${$connection.latency}ms` : ''}"
  aria-label="Connection status: {$connection.status}"
>
  <span class="conn-dot" aria-hidden="true"></span>
  <span class="conn-label">{$connection.status}</span>
  {#if $connection.latency !== null && $connection.status === "connected"}
    <span class="conn-latency">{$connection.latency}ms</span>
  {/if}
</button>

<style>
  .conn-pill {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 10px;
    background: transparent;
    border: 1px solid var(--border-default);
    cursor: pointer;
    transition: border-color var(--transition-fast);
    min-height: unset;
    font-family: var(--font-mono);
    font-size: 0.65rem;
  }

  .conn-pill:hover { border-color: var(--border-active); }

  .conn-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--status-offline);
    transition: background var(--transition-base), box-shadow var(--transition-base);
  }

  .connected .conn-dot    { background: var(--status-nominal); box-shadow: 0 0 5px var(--status-nominal); }
  .connecting .conn-dot   { background: var(--status-warning); animation: blink 0.8s ease-in-out infinite; }
  .disconnected .conn-dot { background: var(--status-critical); }

  .conn-label {
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .connected .conn-label    { color: var(--status-nominal); }
  .connecting .conn-label   { color: var(--status-warning); }
  .disconnected .conn-label { color: var(--status-critical); }

  .conn-latency {
    color: var(--text-dim);
    font-size: 0.6rem;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
  }
</style>
