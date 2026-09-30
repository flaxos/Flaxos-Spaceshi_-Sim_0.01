import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(path.join(tmpdir(), 'flaxos-frontend-regression-'));
after(() => rm(temporary, { recursive: true, force: true }));
const bundle = path.join(temporary, 'stores.mjs');
await build({
  stdin: { contents: [
    'export * from "./src/lib/stores/gameState.ts";',
    'export * from "./src/lib/stores/playerShip.ts";',
    'export * from "./src/lib/stores/crewSession.ts";',
    'export * from "./src/lib/stores/missionState.ts";',
    'export * from "./src/lib/stores/selectedTarget.ts";',
  ].join('\n'), resolveDir: frontend, loader: 'ts' },
  outfile: bundle, bundle: true, format: 'esm', platform: 'node',
  plugins: [{ name: 'transport-fixture', setup(b) {
    b.onResolve({ filter: /(?:^|\/)wsClient\.js$/ }, () => ({ path: 'fixture', namespace: 'fixture' }));
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const wsClient = globalThis.__crewTestTransport;', loader: 'js' }));
  } }],
});
let fixtureId = 0;
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
function read(store) { let current; const unsubscribe = store.subscribe(s => { current = s; }); unsubscribe(); return current; }

function clock(t) {
  const real = { setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  let now = 0, sequence = 0;
  const timers = new Map();
  globalThis.setTimeout = (fn, ms = 0) => { const id = ++sequence; timers.set(id, { fn, due: now + ms }); return id; };
  globalThis.clearTimeout = id => timers.delete(id);
  t.after(() => Object.assign(globalThis, real));
  return { get now() { return now; }, async advance(ms) {
    const target = now + ms;
    while (true) {
      const next = [...timers].sort((a, b) => a[1].due - b[1].due)[0];
      if (!next || next[1].due > target) break;
      now = next[1].due; timers.delete(next[0]); next[1].fn(); await settle();
    }
    now = target; await settle();
  } };
}

async function fixture(t) {
  const time = clock(t), listeners = new Map(), requests = [], holds = new Map();
  const ws = {
    status: 'disconnected', activeShipId: null,
    session: { ship_id: null, station: null }, rejectClaim: false,
    mission: { available: true, mission_epoch: 1, current_scenario_id: '07_docking_test', mission_status: 'in_progress' },
    get isConnected() { return this.status === 'connected'; },
    setActiveShipId(id) { this.activeShipId = id; },
    addEventListener(name, handler) { const list = listeners.get(name) ?? []; list.push(handler); listeners.set(name, list); },
    emit(name, detail) { if (name === 'status_change') this.status = detail.status; for (const fn of listeners.get(name) ?? []) fn({ detail }); },
    connect() { this.emit('status_change', { status: 'connected' }); return Promise.resolve(); },
    handlers: {},
    send(cmd, args = {}) {
      requests.push({ cmd, args, t: time.now });
      if (!this.isConnected) return Promise.reject(new Error('Not connected'));
      if (holds.has(cmd)) { const d = holds.get(cmd); holds.delete(cmd); return d.promise; }
      if (this.handlers[cmd]) return Promise.resolve(this.handlers[cmd](args));
      if (cmd === 'my_status') return Promise.resolve({ ok: true, response: { client_id: 'client_test', ...this.session } });
      if (cmd === 'assign_ship') { this.session.ship_id = args.ship; return Promise.resolve({ ok: true }); }
      if (cmd === 'claim_station') {
        if (this.rejectClaim) return Promise.resolve({ ok: false, error: 'Station claimed by another crew member' });
        this.session.station = args.station; return Promise.resolve({ ok: true });
      }
      if (cmd === 'release_station') { this.session.station = null; return Promise.resolve({ ok: true }); }
      if (cmd === 'get_mission') return Promise.resolve({ ok: true, mission: { ...this.mission } });
      if (cmd === 'get_events') return Promise.resolve({ ok: true, events: [{ t: time.now / 1000 + 1, type: 'crew_test' }] });
      if (cmd === 'get_state') return Promise.resolve({ ok: true, t: time.now / 1000, mission_epoch: this.mission.mission_epoch, state: args.ship ? { id: args.ship } : undefined });
      return Promise.resolve({ ok: true });
    },
  };
  globalThis.__crewTestTransport = ws;
  t.after(() => { delete globalThis.__crewTestTransport; });
  const stores = await import(`${pathToFileURL(bundle)}?fixture=${++fixtureId}`);
  const hold = cmd => { const d = deferred(); holds.set(cmd, d); return d; };
  return { stores, ws, requests, time, hold, async connect() { stores.initializeCrewSession(); stores.initializeConnection(); await settle(); } };
}

test('in-flight ship switch publishes only the new ship and continues both poll chains', async t => {
  const f = await fixture(t); await f.connect();
  const old = f.hold('get_state'); f.stores.startPolling('ship_A'); await settle();
  f.stores.startPolling('ship_B'); await settle();
  assert.equal(read(f.stores.gameState).state.id, 'ship_B');
  old.resolve({ ok: true, state: { id: 'ship_A', systems: { secret: true } } }); await settle();
  assert.equal(read(f.stores.gameState).state.id, 'ship_B');
  const stateBefore = f.requests.filter(r => r.cmd === 'get_state' && r.args.ship === 'ship_B').length;
  const eventBefore = f.requests.filter(r => r.cmd === 'get_events').length;
  await f.time.advance(3000);
  assert(f.requests.filter(r => r.cmd === 'get_state' && r.args.ship === 'ship_B').length > stateBefore + 10);
  assert(f.requests.filter(r => r.cmd === 'get_events').length > eventBefore + 2);
});

test('role changes clear cached privileged fields and require a fresh full snapshot', async t => {
  const f = await fixture(t); await f.connect();
  f.ws.session = { ship_id: 'ship_A', station: 'captain' };
  f.ws.handlers.get_state = () => ({ ok: true, state: { id: 'ship_A', weapons: { ammunition: 12 } }, mission_epoch: 1, t: 1 });
  await f.stores.refreshCrewSession(); await settle();
  assert.equal(read(f.stores.gameState).state.weapons.ammunition, 12);
  f.ws.session.station = 'engineering';
  const full = f.hold('get_state');
  await f.stores.refreshCrewSession(); await settle();
  assert.deepEqual(read(f.stores.gameState), {});
  assert.equal(f.requests.filter(r => r.cmd === 'get_state').at(-1).args.full, true);
  full.resolve({ _delta: true, state: { engineering: { reactor_output: 400 } } }); await settle();
  assert.deepEqual(read(f.stores.gameState), {}, 'a delta without a baseline cannot leak old role fields');
  f.ws.handlers.get_state = () => ({ ok: true, state: { id: 'ship_A', engineering: { reactor_output: 400 } }, t: 1, mission_epoch: 1 });
  await f.time.advance(200);
  assert.equal(read(f.stores.gameState).state.weapons, undefined);
  assert.equal(read(f.stores.crewSession).station, 'engineering');
});

test('nested session authority governs claims, claim rejection, release and explicit rejoin', async t => {
  const f = await fixture(t); await f.connect();
  assert.equal(await f.stores.joinCrewStation('ship_A', 'helm'), true);
  assert.equal(read(f.stores.crewSession).station, 'helm');
  assert.equal(f.ws.activeShipId, 'ship_A');
  f.ws.rejectClaim = true;
  assert.equal(await f.stores.joinCrewStation('ship_A', 'engineering'), false);
  assert.equal(read(f.stores.crewSession).station, 'helm', 'button intent does not override server authority');
  assert.match(read(f.stores.crewSession).error, /another crew member/);
  const oldState = f.hold('get_state'); f.stores.startPolling('ship_A'); await settle();
  f.ws.emit('status_change', { status: 'disconnected' });
  assert.equal(read(f.stores.crewSession).shipId, null);
  assert.equal(read(f.stores.crewSession).station, null);
  assert.equal(f.ws.activeShipId, null);
  assert.deepEqual(read(f.stores.gameState), {});
  const before = f.requests.length;
  f.ws.emit('status_change', { status: 'connected' }); await settle();
  oldState.resolve({ ok: true, state: { id: 'ship_A', weapons: { old: true } } }); await settle();
  await f.time.advance(2500);
  assert.equal(read(f.stores.crewSession).needsRejoin, true);
  assert.equal(read(f.stores.crewSession).shipId, null, 'retained server assignment alone does not silently rejoin');
  assert.equal(f.requests.slice(before).filter(r => ['assign_ship', 'claim_station'].includes(r.cmd)).length, 0);
  assert.equal(read(f.stores.gameState).state, undefined);
  f.ws.rejectClaim = false;
  assert.equal(await f.stores.joinCrewStation('ship_A', 'engineering'), true);
  assert.equal(read(f.stores.crewSession).needsRejoin, false);
  assert.equal(read(f.stores.crewSession).station, 'engineering');
  await f.stores.releaseCrewStation();
  assert.equal(read(f.stores.crewSession).station, null);
});

test('same-time epoch change clears old telemetry and mission watcher survives success/failure/reset', async t => {
  const f = await fixture(t); await f.connect();
  await f.stores.joinCrewStation('ship_A', 'helm');
  f.ws.handlers.get_state = () => ({ ok: true, t: 0, mission_epoch: 1, state: { id: 'ship_A', old_projectiles: [1] } });
  f.stores.startPolling('ship_A'); await settle();
  f.stores.selectedTargetId.set('old_target');
  f.ws.mission.mission_status = 'success'; await f.time.advance(1000);
  assert.equal(read(f.stores.missionState).mission_status, 'success');
  f.ws.mission.mission_status = 'failure'; await f.time.advance(1000);
  assert.equal(read(f.stores.missionState).mission_status, 'failure');
  f.ws.mission.mission_epoch = 2; f.ws.mission.mission_status = 'in_progress';
  f.ws.handlers.get_state = () => ({ _delta: true, t: 0, mission_epoch: 2 });
  await f.time.advance(200);
  assert.deepEqual(read(f.stores.gameState), {}, 'epoch invalidates old state even without time rollback');
  assert.equal(read(f.stores.selectedTargetId), '', 'shared reset clears a target from the old mission');
  f.ws.handlers.get_state = args => ({ ok: true, t: 0, mission_epoch: 2, state: { id: 'ship_A', fresh: args.full } });
  await f.time.advance(1000);
  assert.equal(read(f.stores.missionState).mission_status, 'in_progress');
  assert.equal(read(f.stores.gameState).state.old_projectiles, undefined);
  assert.equal(read(f.stores.gameState).mission_epoch, 2);
});

const transportBundle = path.join(temporary, 'transport.mjs');
await build({
  stdin: { contents: 'export * from "./src/lib/ws/wsClient.ts"; export * from "./src/lib/stores/commandFeedback.ts";', resolveDir: frontend, loader: 'ts' },
  outfile: transportBundle, bundle: true, format: 'esm', platform: 'node',
});

async function transportFixture(t) {
  const time = clock(t);
  const saved = { window: globalThis.window, WebSocket: globalThis.WebSocket };
  globalThis.window = { location: { hostname: 'localhost', search: '' } };
  globalThis.WebSocket = { OPEN: 1, CONNECTING: 0 };
  t.after(() => Object.assign(globalThis, saved));
  const module = await import(`${pathToFileURL(transportBundle)}?fixture=${++fixtureId}`);
  const messages = [];
  module.wsClient.socket = { readyState: 1, send: raw => messages.push(JSON.parse(raw)) };
  module.wsClient.status = 'connected';
  return { ...module, time, messages, reply(data) { module.wsClient._handleMessage(JSON.stringify({ type: 'response', data })); } };
}

test('late unknown-ID and ID-less replies cannot steal a pending state/claim response', async t => {
  const f = await transportFixture(t);
  let settled = false;
  const state = f.wsClient.send('get_state').then(r => { settled = true; return r; });
  const id = f.messages.at(-1)._request_id;
  f.reply({ _request_id: id + 100, ok: true, message: 'Late response' });
  f.reply({ ok: true, message: 'Unsolicited heartbeat' }); await settle();
  assert.equal(settled, false);
  f.wsClient.sendAsync('heartbeat');
  const heartbeat = f.messages.at(-1)._request_id;
  assert.notEqual(heartbeat, id);
  f.reply({ _request_id: heartbeat, ok: true }); await settle();
  assert.equal(settled, false);
  f.reply({ _request_id: id, ok: true, state: { id: 'ship_A' } });
  assert.equal((await state).state.id, 'ship_A');
});

test('ignored ship command rejections and transport failures produce shared visible feedback', async t => {
  const f = await transportFixture(t);
  f.wsClient.setActiveShipId('ship_A');
  const action = f.wsClient.sendShipCommand('set_throttle', { throttle: 0.5 });
  f.reply({ _request_id: f.messages.at(-1)._request_id, ok: false, error: 'Requires helm station' });
  await action;
  assert.deepEqual(read(f.commandFeedback), { command: 'set_throttle', message: 'Requires helm station' });
  f.wsClient.socket = null;
  await assert.rejects(f.wsClient.sendShipCommand('dock', { target: 'station' }), /Not connected/);
  assert.deepEqual(read(f.commandFeedback), { command: 'dock', message: 'Not connected' });
});
