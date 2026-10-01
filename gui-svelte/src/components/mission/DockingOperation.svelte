<script lang="ts">
  import { onMount } from "svelte";
  import { crewSession } from "../../lib/stores/crewSession.js";
  import { crewAssistance, stationCoverage, watchCrewAssistance } from "../../lib/stores/crewAssistance.js";
  onMount(watchCrewAssistance);
</script>

<section class="docking-operation" aria-label="Docking crew guide">
  <h3>Docking crew guide</h3>
  <p class="assignment">Your station: {$crewSession.station?.toUpperCase() ?? "UNASSIGNED"}</p>
  <dl class="crew-coverage" aria-label="Current station coverage">
    <div><dt>Helm</dt><dd>{stationCoverage($crewAssistance, "helm")}</dd></div>
    <div><dt>Engineering</dt><dd>{stationCoverage($crewAssistance, "engineering")}</dd></div>
  </dl>
  <ol>
    <li><strong>Helm:</strong> select Tycho Station, choose CPU ASSIST, select that contact in the flight computer and APPROVE rendezvous. In Nav Tools, REQUEST DOCK on the same contact.</li>
    <li><strong>Engineering:</strong> choose MANUAL to use Engineering Control. Monitor fuel and thermal state; coordinate the drive governor with Helm. Restore the drive limit to 100% for the approach.</li>
    <li><strong>Final approach:</strong> 5 km is an approach milestone. Docking requires at most 50 m and 1 m/s relative speed. The request can wait while rendezvous approaches.</li>
    <li><strong>After docking:</strong> choose MANUAL at Helm. In Manual Flight, manually set Helm thrust to zero (Throttle 0%) and confirm actual output. Replay uses existing captain/admin authority; undocking is optional.</li>
  </ol>
  <p class="assist-limits">Solo: prepare any Engineering settings before releasing that seat and joining Helm. You approve the navigation program. Unclaimed Engineering CPU only watches heat sinks when fitted; it does not manage the reactor or drive governor. CPU ASSIST is a control tier, not a complete replacement crew.</p>
</section>

<style>
  .docking-operation { margin: var(--space-sm) 0; padding: var(--space-sm); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-input); font-size: var(--font-size-xs); }
  h3 { margin: 0 0 var(--space-xs); font-size: var(--font-size-base); }
  .assignment { color: var(--hud-primary); font-family: var(--font-mono); }
  .crew-coverage { margin: var(--space-sm) 0; }
  .crew-coverage div { display: grid; grid-template-columns: 7rem 1fr; gap: var(--space-xs); margin: 4px 0; }
  dt { font-weight: 600; } dd { margin: 0; }
  ol { padding-left: 1.3rem; } li { margin-bottom: var(--space-xs); line-height: 1.5; }
  .assist-limits { color: var(--text-secondary); line-height: 1.5; margin-bottom: 0; }
</style>
