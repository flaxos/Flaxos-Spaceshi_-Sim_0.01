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
  gameState: writable({}), missionState: writable(null), crewSession: writable({ station: 'helm' }),
  tier: writable('cpu-assist'), selectedHelmTargetId: writable(''), coverage: writable(null),
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
  ].join('\n'), resolveDir: frontend, loader: 'ts' },
  outfile: bundle, bundle: true, format: 'esm', platform: 'node',
  plugins: [{ name: 'controlled-render', setup(b) {
    b.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, 'utf8'),
      { filename: args.path, generate: 'server' }).js.code, loader: 'js' }));
    b.onResolve({ filter: /(?:gameState|missionState|crewSession|tier|helmUi|wsClient|crewAssistance)\.js$/ },
      args => ({ path: path.basename(args.path, '.js'), namespace: 'fixture' }));
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => {
      if (args.path === 'wsClient') return { contents: 'export const wsClient = { addEventListener() {}, status: "disconnected" };', loader: 'js' };
      if (args.path === 'crewAssistance') return { contents: `export const crewAssistance = globalThis.__dockingUiStores.coverage;
        export const watchCrewAssistance = () => () => {};
        export { stationCoverage } from ${JSON.stringify(path.join(frontend, 'src/lib/stores/crewAssistance.ts'))};`, loader: 'js', resolveDir: frontend };
      const names = args.path === 'helmUi' ? ['selectedHelmTargetId'] : [args.path];
      return { contents: names.map(n => `export const ${n} = globalThis.__dockingUiStores.${n};`).join('\n'), loader: 'js' };
    });
  } }],
});
const ui = await import(pathToFileURL(bundle));
const render = component => ui.render(component).body;

test('mission summary retains full briefing and existing docking station instructions', () => {
  stores.missionState.set({ available: true, current_scenario_id: '07_docking_test', name: 'Docking Test',
    description: 'Short summary', briefing: 'Detailed existing operation', mission_status: 'in_progress',
    objectives: { dock: { description: 'Dock with Tycho Station', status: 'pending', type: 'dock_with' } } });
  const html = render(ui.MissionObjectives);
  for (const text of ['Short summary', 'Detailed existing operation', 'Docking crew guide', 'Engineering',
    'at most 50 m and 1 m/s', 'manually set Helm thrust to zero', 'Coverage unavailable']) assert(html.includes(text), text);
  stores.missionState.set({ available: true, current_scenario_id: 'other', name: 'Another mission' });
  assert(!render(ui.MissionObjectives).includes('Docking crew guide'), 'guidance must not invent tasks for other missions');
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
