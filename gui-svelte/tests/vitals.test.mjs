import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const temporary = await mkdtemp(join(tmpdir(), 'flaxos-vitals-'));
const bundled = join(temporary, 'vitals.mjs');
await build({
  entryPoints: [new URL('../src/components/helm/helmData.ts', import.meta.url).pathname],
  outfile: bundled, bundle: true, format: 'esm', platform: 'node',
});
const { getFuelPercent, getHullPercent, getThrottle, getAutopilotSnapshot } = await import(pathToFileURL(bundled));
after(() => rm(temporary, { recursive: true, force: true }));

test('Helm and common status use canonical fuel, including a nearly empty tank', () => {
  assert.equal(getFuelPercent({ fuel: { percent: 99.5 } }), 99.5);
  assert.equal(getFuelPercent({ fuel: { percent: 0.5 } }), 0.5);
  assert.equal(getFuelPercent({ fuel: { percent: 0 } }), 0);
});

test('a ship with 150 integrity has 100% hull; damage uses its actual maximum', () => {
  assert.equal(getHullPercent({ hull_integrity: 150, max_hull_integrity: 150 }), 100);
  assert.equal(getHullPercent({ hull_integrity: 75, max_hull_integrity: 150 }), 50);
  assert.equal(getHullPercent({ hull_integrity: 150, max_hull_integrity: 150, hull_percent: 80 }), 80);
});

test('drive telemetry shows Engineering-governed output rather than Helm request', () => {
  const ship = { throttle: 0.5, helm: { manual_throttle: 0.8 } };
  assert.equal(getThrottle(ship), 0.5);
  assert.equal(getThrottle({ ...ship, throttle: 0 }), 0);
});

test('absent, invalid or role-filtered telemetry cannot imply empty fuel or full hull', () => {
  assert.equal(getFuelPercent({}), null);
  assert.equal(getFuelPercent({ fuel: { percent: Number.NaN } }), null);
  assert.equal(getHullPercent({}), null);
  assert.equal(getHullPercent({ hull_integrity: 0, max_hull_integrity: 0 }), null);
});

test('the shared navigation target follows the active program, independently of weapon targeting', () => {
  const nav = getAutopilotSnapshot({
    autopilot_program: 'rendezvous', autopilot_state: { target_id: 'C004' }, target_id: 'C009',
  });
  assert.equal(nav.program, 'rendezvous');
  assert.equal(nav.targetId, 'C004');
});
