// Controlled rendering of actual Svelte components; not live-stack proof.
import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { writable } from 'svelte/store';
import { compile } from 'svelte/compiler';
import { build } from 'esbuild';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(path.join(tmpdir(), 'flaxos-mission-ui-'));
after(() => rm(temporary, { recursive: true, force: true }));
const stores = {
  gameState: writable({}), missionState: writable(null), crewSession: writable({ station: 'helm', connected: true, registered: true, shipId: 'ship_A',
    needsRejoin: false, busy: false, availableCommands: ['get_target_solution'], authorityRevision: 1 }),
  tier: writable('cpu-assist'), selectedHelmTargetId: writable(''), selectedTacticalTargetId: writable(''), coverage: writable(null),
};
globalThis.__dockingUiStores = stores;
after(() => { delete globalThis.__dockingUiStores; });
const bundle = path.join(temporary, 'components.mjs');
await build({
  stdin: { contents: [
    'export { render } from "svelte/server";',
    'export { default as MissionObjectives } from "./src/components/mission/MissionObjectives.svelte";',
    'export { default as DockingPanel } from "./src/components/helm/DockingPanel.svelte";',
    'export { default as EngineeringControlPanel } from "./src/components/engineering/EngineeringControlPanel.svelte";',
    'export { default as TargetingDisplay } from "./src/components/tactical/TargetingDisplay.svelte";',
    'export { default as FiringSolutionDisplay } from "./src/components/tactical/FiringSolutionDisplay.svelte";',

  ].join('\n'), resolveDir: frontend, loader: 'ts' },
  outfile: bundle, bundle: true, format: 'esm', platform: 'node',
  plugins: [{ name: 'controlled-render', setup(b) {
    b.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, 'utf8'),
      { filename: args.path, generate: 'server' }).js.code, loader: 'js' }));
    b.onResolve({ filter: /(?:gameState|missionState|crewSession|tier|helmUi|tacticalUi|wsClient|crewAssistance)\.js$/ },
      args => ({ path: path.basename(args.path, '.js'), namespace: 'fixture' }));
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => {
      if (args.path === 'wsClient') return { contents: 'export const wsClient = { addEventListener() {}, status: "connected", isConnected: true };', loader: 'js' };
      if (args.path === 'crewAssistance') return { contents: `export const crewAssistance = globalThis.__dockingUiStores.coverage;
        export const watchCrewAssistance = () => () => {};
        export { stationCoverage, isDockingGuideScenario } from ${JSON.stringify(path.join(frontend, 'src/lib/stores/crewAssistance.ts'))};`, loader: 'js', resolveDir: frontend };
      const names = args.path === 'helmUi' ? ['selectedHelmTargetId'] : args.path === 'tacticalUi' ? ['selectedTacticalTargetId'] : [args.path];
      return { contents: names.map(n => `export const ${n} = globalThis.__dockingUiStores.${n};`).join('\n'), loader: 'js' };
    });
  } }],
});
const ui = await import(pathToFileURL(bundle));
const render = component => ui.render(component).body;

test('both Tycho docking missions retain the briefing, manual cutoff and existing crew limits', () => {
  for (const scenario of ['01_tutorial_intercept', '07_docking_test']) {
    stores.missionState.set({ available: true, current_scenario_id: scenario, name: 'Docking mission',
      description: 'Short summary', briefing: 'Detailed existing operation', mission_status: 'in_progress',
      objectives: { dock: { description: 'Dock with Tycho Station', status: 'pending', type: 'dock_with' } } });
    const html = render(ui.MissionObjectives);
    for (const text of ['Short summary', 'Detailed existing operation', 'Docking crew guide', 'Engineering',
      'at most 50 m and 1 m/s', 'manually set Helm thrust to zero', 'Coverage unavailable',
      'choose MANUAL at Helm', 'In Manual Flight', 'Throttle 0%',
      'does not manage the reactor or drive governor', 'CPU ASSIST is a control tier']) assert(html.includes(text), `${scenario}: ${text}`);
  }
  for (const scenario of ['other', '02_combat_destroy', null, undefined]) {
    stores.missionState.set({ available: true, current_scenario_id: scenario, name: 'Another mission' });
    assert(!render(ui.MissionObjectives).includes('Docking crew guide'), 'guidance must not invent tasks for other missions');
  }
  stores.missionState.set({ available: false, current_scenario_id: '01_tutorial_intercept' });
  assert(!render(ui.MissionObjectives).includes('Docking crew guide'), 'unloaded missions do not show a guide');
});

test('docking faults and missing telemetry are not rendered as approach or readiness', () => {
  for (const [status, label] of [['offline', 'OFFLINE'], ['target_lost', 'TARGET LOST']]) {
    stores.gameState.set({ state: { docking: { status } } });
    const html = render(ui.DockingPanel);
    assert(html.includes(label)); assert(!html.includes('APPROACHING'));
  }
  stores.gameState.set({ state: {} });
  assert(render(ui.DockingPanel).includes('UNKNOWN'));
});

test('an empty Engineering proposal queue does not assert stable automatic control', () => {
  stores.gameState.set({ state: {} }); stores.tier.set('cpu-assist');
  const html = render(ui.EngineeringControlPanel);
  assert(html.includes('No pending proposals'));
  assert(html.includes('an empty queue does not confirm automatic control'));
  assert(!html.includes('Auto-ops is holding') && !html.includes('>Stable<'));
});


test('compiled targeting displays clear embedded solutions for acquiring, unlock and a different selected contact', () => {
  stores.tier.set('raw');
  const snapshot = lock_state => ({ mission_epoch: 1, state: { id: 'ship_A', sensors: { contacts: [{ id: 'target_A' }, { id: 'nav_target' }] }, targeting: {
    lock_state, locked_target: 'target_A', lock_quality: 0.9,
    solutions: { railgun: { confidence: 0.83, time_of_flight: 123 } },
  } } });
  stores.selectedTacticalTargetId.set('target_A');
  stores.gameState.set(snapshot('locked'));
  assert(render(ui.FiringSolutionDisplay).includes('83%'), 'confirmed lock preserves embedded solution');
  assert(render(ui.TargetingDisplay).includes('83%'));
  for (const state of ['acquiring', 'idle', 'tracking']) {
    stores.gameState.set(snapshot(state));
    assert(!render(ui.FiringSolutionDisplay).includes('83%'), state);
    assert(!render(ui.TargetingDisplay).includes('83%'), state);
  }
  stores.gameState.set(snapshot('locked'));
  stores.selectedTacticalTargetId.set('nav_target');
  assert(!render(ui.TargetingDisplay).includes('83%'), 'a nav-selected contact cannot inherit another target solution');
  stores.crewSession.update(session => ({ ...session, availableCommands: null, authorityRevision: 2 }));
  assert(!render(ui.FiringSolutionDisplay).includes('83%'), 'failed authority verification clears solution fallback');
});
