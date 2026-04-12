<script lang="ts">
  const VIEW_NAME = "Science";
</script>

<div class="view-root">
  <div class="stub-content">
    <div class="stub-title">{VIEW_NAME}</div>
    <div class="stub-hint">Implementation in progress — Prompt 3+</div>
  </div>
</div>

<style>
  .view-root {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: var(--space-xs);
    padding: var(--space-xs);
    overflow: hidden;
  }
  .stub-content {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: var(--space-sm);
  }
  .stub-title {
    font-family: var(--font-mono);
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: 4px;
    color: var(--tier-accent, var(--hud-primary));
    text-transform: uppercase;
    opacity: 0.6;
  }
  .stub-hint {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    letter-spacing: 1px;
  }
</style>
