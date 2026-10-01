import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'svelte/compiler';
import { build } from 'esbuild';

// Actual compiled component and native browser events; transport/session are
// explicit fixtures. Separate real WS/TCP evidence remains required for UAT.
const require = createRequire(import.meta.url);
const { chromium } = require('../../node_modules/playwright');
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixtureSource = `
  import { writable } from 'svelte/store';
  export const gameState = writable({ state: { id: 'player', throttle: 0 } });
  export const crewSession = writable({ connected: true, registered: true, shipId: 'player',
    station: 'helm', busy: false, needsRejoin: false, availableCommands: ['set_thrust'], authorityRevision: 1 });
  export const tier = writable('manual');
  export const wsClient = { isConnected: true, sendShipCommand: async (command, args) => {
    window.__thrustCommands.push({ command, args });
    if (window.__deferThrust) return new Promise(resolve => window.__thrustReplies.push(resolve));
    return { ok: true };
  } };
`;
const bundle = await build({
  stdin: { contents: `
    import { mount, unmount, tick } from 'svelte';
    import ManualFlightPanel from './src/components/helm/ManualFlightPanel.svelte';
    import { gameState, crewSession, wsClient } from 'cutoff-fixture';
    window.__thrustCommands = [];
    window.__thrustReplies = [];
    let session; crewSession.subscribe(value => session = value);
    const component = mount(ManualFlightPanel, { target: document.body });
    window.__telemetry = async throttle => { gameState.set({ state: { id: 'player', throttle } }); await tick(); };
    window.__authority = async change => { session = { ...session, ...change }; crewSession.set(session); await tick(); };
    window.__unmount = () => unmount(component);
  `, resolveDir: frontend, loader: 'ts' },
  write: false, bundle: true, platform: 'browser', format: 'iife', conditions: ['browser'],
  plugins: [{ name: 'component-fixtures', setup(b) {
    b.onResolve({ filter: /(?:^cutoff-fixture$|\/(?:wsClient|gameState|crewSession|tier)\.js$)/ }, () => ({ path: 'cutoff-fixture', namespace: 'fixture' }));
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: fixtureSource, loader: 'js', resolveDir: frontend }));
    b.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, 'utf8'),
      { filename: args.path, generate: 'client', css: 'injected' }).js.code, loader: 'js' }));
  } }],
});
let browser;
before(async () => { browser = await chromium.launch({ ...(process.env.FLAXOS_CHROMIUM ? { executablePath: process.env.FLAXOS_CHROMIUM } : {}), args: ['--no-sandbox'] }); });
after(async () => { await browser?.close(); });
async function panel(t) {
  const context = await browser.newContext(); t.after(() => context.close());
  const page = await context.newPage(); page.setDefaultTimeout(1500);
  await page.setContent('<!doctype html><body></body>');
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const input = page.locator('.throttle input[type=number]');
  await input.waitFor();
  return { page, input, commands: () => page.evaluate(() => window.__thrustCommands),
    telemetry: value => page.evaluate(value => window.__telemetry(value), value),
    authority: change => page.evaluate(change => window.__authority(change), change),
    async sent(count) { await page.waitForFunction(count => window.__thrustCommands.length === count, count, { timeout: 1000 }); } };
}

test('editing stale zero and blurring emits one normal cutoff command even without change', async t => {
  const f = await panel(t);
  // The fixture intentionally exposes the stale displayed zero from the native
  // failing case; a current nonzero backend must not be inferred from the field.
  await f.input.fill('0'); await f.input.press('Tab'); await f.sent(1);
  assert.deepEqual((await f.commands()).map(c => [c.command, c.args.thrust]), [['set_thrust', 0]]);
});

test('telemetry cannot overwrite an uncommitted zero draft; change plus blur sends once', async t => {
  const f = await panel(t); await f.telemetry(.2);
  await f.input.fill('0'); await f.telemetry(.25);
  assert.equal(await f.input.inputValue(), '0');
  await f.input.press('Tab'); await f.sent(1);
  await f.page.waitForTimeout(100);
  assert.equal((await f.commands()).length, 1);
  assert.equal((await f.commands())[0].args.thrust, 0);
});

test('explicit cutoff works repeatedly at displayed zero and for authorized Captain', async t => {
  const f = await panel(t);
  await f.authority({ station: 'captain' });
  const cutoff = f.page.getByRole('button', { name: 'CUT THRUST', exact: true });
  await cutoff.click(); await f.sent(1);
  await f.page.waitForTimeout(100);
  await cutoff.click(); await f.sent(2);
  assert.deepEqual((await f.commands()).map(c => c.args.thrust), [0, 0]);
});

test('normal nonzero number and range retain their existing authorized thrust values', async t => {
  const f = await panel(t);
  await f.input.fill('20'); await f.input.press('Tab'); await f.sent(1);
  await f.page.waitForTimeout(100);
  await f.page.locator('.throttle input[type=range]').fill('35'); await f.sent(2);
  assert.deepEqual((await f.commands()).map(c => c.args.thrust), [.2, .35]);
});

test('observer and wrong seat cannot issue thrust; explicit verified rejoin restores control', async t => {
  const f = await panel(t);
  for (const change of [{ shipId: null, station: null, needsRejoin: true, availableCommands: [] },
    { shipId: 'player', station: 'engineering', needsRejoin: false, availableCommands: ['set_reactor_output'] }]) {
    await f.authority(change);
    assert.equal(await f.input.isDisabled(), true);
    assert.equal(await f.page.getByRole('button', { name: 'CUT THRUST', exact: true }).isDisabled(), true);
  }
  assert.deepEqual(await f.commands(), []);
  await f.authority({ shipId: 'player', station: 'helm', needsRejoin: false, availableCommands: ['set_thrust'], authorityRevision: 2 });
  await f.page.getByRole('button', { name: 'CUT THRUST', exact: true }).click(); await f.sent(1);
});

test('plain blur, blank or invalid draft does not imply zero intent', async t => {
  const f = await panel(t);
  await f.input.focus(); await f.input.press('Tab');
  await f.input.fill(''); await f.input.press('Tab');
  await f.input.fill('101'); await f.input.press('Tab');
  await f.page.waitForTimeout(100);
  assert.deepEqual(await f.commands(), []);
  await f.input.fill('0'); await f.input.press('Tab'); await f.sent(1);
  await f.input.fill('0'); await f.input.press('Tab'); await f.sent(2);
  assert.deepEqual((await f.commands()).map(c => c.args.thrust), [0, 0]);
});

test('pending throttle intent retires after authority change and unmount', async t => {
  const f = await panel(t);
  // Retire before the real 40 ms timer in one browser task, without relying
  // on multiple protocol round-trips completing before that deadline.
  await f.page.evaluate(async () => {
    const input = document.querySelector('.throttle input[type=number]');
    input.value = '20'; input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await window.__authority({ shipId: 'another_ship', authorityRevision: 2 });
  });
  await f.page.waitForTimeout(100);
  assert.deepEqual(await f.commands(), [], 'an old edit must not target a newly selected ship');
  await f.page.evaluate(async () => {
    const input = document.querySelector('.throttle input[type=number]');
    input.value = '25'; input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await window.__unmount();
  });
  await f.page.waitForTimeout(100);
  assert.deepEqual(await f.commands(), [], 'unmount cancels the pending debounce');
});

test('late throttle acknowledgements cannot replace feedback for a newer intent or authority', async t => {
  const f = await panel(t);
  await f.page.evaluate(() => { window.__deferThrust = true; });
  await f.input.fill('20'); await f.input.press('Tab'); await f.sent(1);
  await f.page.getByRole('button', { name: 'CUT THRUST', exact: true }).click(); await f.sent(2);
  await f.page.evaluate(() => {
    window.__thrustReplies[1]({ ok: true });
    window.__thrustReplies[0]({ ok: false, error: 'retired action denial' });
  });
  assert.equal(await f.page.locator('.feedback').count(), 0);
  await f.page.getByRole('button', { name: 'CUT THRUST', exact: true }).click(); await f.sent(3);
  await f.authority({ station: null, shipId: null, authorityRevision: 2, needsRejoin: true });
  await f.page.evaluate(() => window.__thrustReplies[2]({ ok: false, error: 'retired authority denial' }));
  assert.equal(await f.page.locator('.feedback').count(), 0);
});
