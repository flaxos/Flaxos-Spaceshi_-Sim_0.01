import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { compile } from 'svelte/compiler';
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
    'export * from "./src/lib/stores/crewPolling.ts";',
    'export { crewCardsFromResponse } from "./src/components/ops/CrewPanel.svelte";',
    'export * from "./src/lib/stores/missionState.ts";',
    'export * from "./src/lib/stores/selectedTarget.ts";',
    'export * from "./src/lib/stores/crewAssistance.ts";',
  ].join('\n'), resolveDir: frontend, loader: 'ts' },
  outfile: bundle, bundle: true, format: 'esm', platform: 'node',
  plugins: [{ name: 'transport-fixture', setup(b) {
    b.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, 'utf8'),
      { filename: args.path, generate: 'server' }).js.code, loader: 'js' }));
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
    sendShipCommand(cmd, args = {}) { return this.send(cmd, { ship: this.activeShipId, ...args }); },
    send(cmd, args = {}) {
      requests.push({ cmd, args, t: time.now });
      if (!this.isConnected) return Promise.reject(new Error('Not connected'));
      if (holds.has(cmd)) { const d = holds.get(cmd); holds.delete(cmd); return d.promise; }
      if (this.handlers[cmd]) return Promise.resolve(this.handlers[cmd](args));
      if (cmd === 'my_status') return Promise.resolve({ ok: true, response: { client_id: 'client_test', available_commands: [], ...this.session } });
      if (cmd === 'assign_ship') { this.session.ship_id = args.ship; return Promise.resolve({ ok: true }); }
      if (cmd === 'claim_station') {
        if (this.rejectClaim) return Promise.resolve({ ok: false, error: 'Station claimed by another crew member' });
        this.session.station = args.station; return Promise.resolve({ ok: true });
      }
      if (cmd === 'release_station') { this.session.station = null; return Promise.resolve({ ok: true }); }
      if (cmd === 'get_mission') return Promise.resolve({ ok: true, mission: { ...this.mission } });
      if (cmd === 'get_events') return Promise.resolve({ ok: true, events: [{ id: time.now + 1, t: time.now / 1000, type: 'crew_test' }] });
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

function coverage(ship, epoch, claimed = false) {
  return { ship_id: ship, stations: [{ station: 'helm', claimed, player: claimed ? 'Helm player' : null },
    { station: 'engineering', claimed: false }], crew_assistance: {
    mission_epoch: epoch, simulation_running: true, worker_running: true, ship_eligible: true, thermal_available: true,
    stations: [{ station: 'helm', active: true, competence: 0.7 }, { station: 'engineering', active: true, competence: 0.7 }],
  } };
}

test('crew assistance distinguishes human ownership, passive seats and conditional heat-sink watch', async t => {
  const f = await fixture(t);
  const data = coverage('ship_A', 1);
  assert.match(f.stores.stationCoverage(null, 'helm'), /unavailable/);
  assert.match(f.stores.stationCoverage(data, 'helm'), /passive/);
  assert.equal(f.stores.stationCoverage(data, 'engineering'), 'CPU heat-sink watch');
  data.crew_assistance.worker_running = false;
  assert.match(f.stores.stationCoverage(data, 'engineering'), /waiting/);
  data.crew_assistance.thermal_available = false;
  assert.match(f.stores.stationCoverage(data, 'engineering'), /no thermal system/);
  data.stations[1] = { station: 'engineering', claimed: true, player: 'Engineer' };
  assert.equal(f.stores.stationCoverage(data, 'engineering'), 'Human: Engineer');
  data.stations[1].claimed = false;
  data.crew_assistance.ship_eligible = false;
  assert.equal(f.stores.stationCoverage(data, 'engineering'), 'Unstaffed');
});

for (const scenario of ['01_tutorial_intercept', '07_docking_test']) {
test(`${scenario}: late crew coverage cannot publish after disconnect, rejoin, role change or same-time epoch reset`, async t => {
  const f = await fixture(t); f.ws.mission.current_scenario_id = scenario; await f.connect();
  f.ws.handlers.station_status = args => ({ ok: true, response: coverage(args.ship, f.ws.mission.mission_epoch, true) });
  const stop = f.stores.watchCrewAssistance(); t.after(stop);
  await f.stores.joinCrewStation('ship_A', 'helm'); await settle();
  assert.equal(read(f.stores.crewAssistance).ship_id, 'ship_A');
  const old = f.hold('station_status'); await f.time.advance(1000);
  f.ws.emit('status_change', { status: 'disconnected' });
  assert.equal(read(f.stores.crewAssistance), null);
  f.ws.session = { ship_id: null, station: null };
  f.ws.emit('status_change', { status: 'connected' }); await settle();
  assert.equal(read(f.stores.crewAssistance), null);
  await f.stores.joinCrewStation('ship_B', 'engineering'); await settle();
  old.resolve({ ok: true, response: coverage('ship_A', 1) }); await settle();
  assert.equal(read(f.stores.crewAssistance).ship_id, 'ship_B');
  const previousEpoch = f.hold('station_status'); await f.time.advance(1000);
  f.ws.mission.mission_epoch = 2; await f.time.advance(1000);
  previousEpoch.resolve({ ok: true, response: coverage('ship_B', 1) }); await settle();
  assert.equal(read(f.stores.crewAssistance).crew_assistance.mission_epoch, 2);
  f.ws.session.station = 'helm'; await f.stores.refreshCrewSession(); await settle();
  f.ws.handlers.station_status = () => ({ ok: true, response: coverage('wrong_ship', 2) });
  await f.time.advance(1000);
  assert.equal(read(f.stores.crewAssistance), null, 'a mismatched server snapshot cannot establish readiness');
  stop(); await f.time.advance(1000);
  assert.equal(read(f.stores.crewAssistance), null);
});
}

test('tutorial crew guidance reads only for an assigned station and stops when leaving the guided mission', async t => {
  const f = await fixture(t);
  f.ws.mission.current_scenario_id = '01_tutorial_intercept';
  f.ws.handlers.station_status = args => ({ ok: true, response: coverage(args.ship, f.ws.mission.mission_epoch, true) });
  const stop = f.stores.watchCrewAssistance(); t.after(stop);
  await f.connect();
  const reads = () => f.requests.filter(row => row.cmd === 'station_status');
  assert.equal(reads().length, 0, 'an observer does not request own-ship assistance');
  await f.stores.joinCrewStation('ship_A', 'helm'); await settle();
  assert.equal(read(f.stores.crewAssistance).ship_id, 'ship_A');
  const old = f.hold('station_status'); await f.time.advance(1000);
  f.ws.mission.current_scenario_id = '02_combat_destroy';
  f.ws.emit('mission_changed', {}); await settle();
  assert.equal(read(f.stores.crewAssistance), null);
  const count = reads().length;
  old.resolve({ ok: true, response: coverage('ship_A', 1, true) }); await settle();
  await f.time.advance(3000);
  assert.equal(read(f.stores.crewAssistance), null, 'late tutorial coverage cannot publish in another mission');
  assert.equal(reads().length, count, 'the coverage poll chain is retired');
  assert(!f.requests.some(row => row.cmd === 'set_thrust'), 'guidance never cuts thrust automatically');
});

test('event identity accepts time zero and distinct paused events while suppressing exact duplicates', async t => {
  const f = await fixture(t); await f.connect();
  let recent = [{ id: 1, t: 0, type: 'paused_first' }];
  f.ws.handlers.get_events = () => ({ ok: true, events: recent });
  f.stores.startPolling('ship_A'); await settle();
  assert.deepEqual(read(f.stores.events).map(e => e.id), [1]);
  recent = [recent[0], { id: 2, t: 0, type: 'paused_second' }];
  await f.time.advance(1000);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [1, 2]);
  recent = [...recent, { id: 3, t: 0, type: 'paused_third' }, { id: 3, t: 0, type: 'paused_third' }];
  await f.time.advance(2000);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [1, 2, 3]);
  assert(f.requests.filter(r => r.cmd === 'get_events').length >= 4);
});

test('successive polls retain different events at a previously consumed nonzero paused timestamp', async t => {
  const f = await fixture(t); await f.connect();
  let recent = [{ id: 10, t: 8, type: 'first' }];
  f.ws.handlers.get_events = () => ({ ok: true, events: recent });
  f.stores.startPolling('ship_A'); await settle();
  assert.deepEqual(read(f.stores.events).map(e => e.id), [10]);
  recent = [...recent, { id: 11, t: 8, type: 'second' }];
  await f.time.advance(1000);
  recent = [...recent, { id: 12, t: 8, type: 'third' }];
  await f.time.advance(2000);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [10, 11, 12]);
});

test('mission epoch retires delayed event replies and rebuilds the ID cursor at unchanged time zero', async t => {
  const f = await fixture(t); await f.connect();
  let recent = [{ id: 40, t: 0, type: 'old_mission' }];
  f.ws.handlers.get_events = () => ({ ok: true, events: recent });
  f.ws.handlers.get_state = () => ({ ok: true, t: 0, mission_epoch: f.ws.mission.mission_epoch, state: { id: 'ship_A' } });
  f.stores.startPolling('ship_A'); await settle();
  assert.deepEqual(read(f.stores.events).map(e => e.id), [40]);
  const old = f.hold('get_events'); await f.time.advance(1000);
  recent = [{ id: 41, t: 0, type: 'new_mission' }]; // runner keeps IDs monotonic across reset
  f.ws.mission.mission_epoch = 2; await f.time.advance(200);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [41]);
  old.resolve({ ok: true, events: [{ id: 42, t: 0, type: 'retired_response' }] }); await settle();
  await f.time.advance(2000);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [41]);
});

test('disconnect and explicit rejoin discard old event replies and permit a new server ID sequence', async t => {
  const f = await fixture(t); await f.connect();
  let recent = [{ id: 90, t: 0, type: 'old_connection' }];
  f.ws.handlers.get_events = () => ({ ok: true, events: recent });
  await f.stores.joinCrewStation('ship_A', 'helm'); await settle();
  assert.deepEqual(read(f.stores.events).map(e => e.id), [90]);
  const old = f.hold('get_events'); await f.time.advance(1000);
  f.ws.session = { ship_id: null, station: null };
  f.ws.emit('status_change', { status: 'disconnected' });
  assert.deepEqual(read(f.stores.events), []);
  recent = [{ id: 1, t: 0, type: 'new_server' }];
  f.ws.emit('status_change', { status: 'connected' }); await settle();
  await f.stores.joinCrewStation('ship_A', 'helm'); await settle();
  old.resolve({ ok: true, events: [{ id: 91, t: 0, type: 'old_reply' }] }); await settle();
  await f.time.advance(2000);
  assert.deepEqual(read(f.stores.events).map(e => e.id), [1]);
});

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


test('background ship reads use only the confirmed server allowlist, including captain expansion', async t => {
  const f = await fixture(t); await f.connect();
  const commands = ['boarding_status', 'drone_status', 'get_draw_profile', 'get_target_solution', 'get_nav_solutions'];
  const reads = () => f.requests.filter(r => commands.includes(r.cmd));
  for (const command of commands) assert.equal(await f.stores.pollShipCommand(command), null);
  assert.equal(reads().length, 0, 'unassigned UI cannot emit station reads');
  f.ws.session = { ship_id: 'ship_A', station: 'helm', available_commands: ['get_nav_solutions'] };
  await f.stores.refreshCrewSession();
  for (const command of commands.slice(0, -1)) assert.equal(await f.stores.pollShipCommand(command), null);
  assert.equal(reads().length, 0, 'Helm background cannot emit Ops, Engineering or Tactical reads');
  assert.deepEqual(await f.stores.pollShipCommand('get_nav_solutions'), { ok: true });
  f.ws.session = { ship_id: 'ship_A', station: 'tactical', available_commands: ['get_target_solution'] };
  await f.stores.refreshCrewSession();
  assert.equal(await f.stores.pollShipCommand('drone_status'), null);
  assert.deepEqual(await f.stores.pollShipCommand('get_target_solution'), { ok: true });
  f.ws.session = { ship_id: 'ship_A', station: 'captain', available_commands: commands };
  await f.stores.refreshCrewSession();
  for (const command of commands) assert.deepEqual(await f.stores.pollShipCommand(command), { ok: true });
  assert.equal(await f.stores.pollShipCommand('drone_status', { ship: 'other_ship' }), null);
  f.ws.handlers.my_status = () => ({ ok: true, response: { ship_id: 'ship_A', station: 'captain' } });
  await f.stores.refreshCrewSession();
  assert.equal(await f.stores.pollShipCommand('drone_status'), null, 'missing permissions fail closed');
  delete f.ws.handlers.my_status; await f.stores.refreshCrewSession();
  assert.deepEqual(await f.stores.pollShipCommand('drone_status'), { ok: true }, 'verified permissions resume automatically');
});

test('in-flight background results retire after role, ship, permissions, mission, disconnect and pending claims', async t => {
  const f = await fixture(t); await f.connect();
  f.ws.session = { ship_id: 'ship_A', station: 'captain', available_commands: ['drone_status'] };
  await f.stores.refreshCrewSession();
  for (const change of ['role', 'ship', 'permissions', 'mission', 'observed_epoch', 'disconnect', 'claim', 'release', 'verification_failure']) {
    // Restore confirmed authority before each independent retirement case.
    if (!f.ws.isConnected) { f.ws.emit('status_change', { status: 'connected' }); await settle(); }
    if (read(f.stores.crewSession).needsRejoin) await f.stores.joinCrewStation('ship_A', 'captain');
    f.ws.session = { ship_id: 'ship_A', station: 'captain', available_commands: ['drone_status'] };
    await f.stores.refreshCrewSession();
    const held = f.hold('drone_status'); const pending = f.stores.pollShipCommand('drone_status');
    let authorityAction;
    if (change === 'role') { f.ws.session.station = 'ops'; await f.stores.refreshCrewSession(); }
    if (change === 'ship') { f.ws.session.ship_id = 'ship_B'; await f.stores.refreshCrewSession(); }
    if (change === 'permissions') { f.ws.session.available_commands = []; await f.stores.refreshCrewSession(); }
    if (change === 'mission') { f.ws.emit('mission_changed', {}); await settle(); }
    if (change === 'observed_epoch') { f.ws.mission.mission_epoch++; await f.time.advance(200); }
    if (change === 'disconnect') f.ws.emit('status_change', { status: 'disconnected' });
    if (change === 'claim') {
      authorityAction = f.hold('assign_ship');
      const joining = f.stores.joinCrewStation('ship_A', 'captain');
      assert.equal(await f.stores.pollShipCommand('drone_status'), null);
      authorityAction.resolve({ ok: false, error: 'Assignment denied' }); await joining;
    }
    if (change === 'release') {
      authorityAction = f.hold('release_station');
      const releasing = f.stores.releaseCrewStation();
      assert.equal(await f.stores.pollShipCommand('drone_status'), null);
      authorityAction.resolve({ ok: false, error: 'Release denied' }); await releasing;
    }
    if (change === 'verification_failure') {
      const failed = f.hold('my_status'); const refreshing = f.stores.refreshCrewSession();
      failed.reject(new Error('Cannot verify authority')); await refreshing;
      assert.equal(await f.stores.pollShipCommand('drone_status'), null);
    }
    held.resolve({ ok: true, confidential: change });
    assert.equal(await pending, null, change);
  }
});

test('nav selection and acquiring do not authorize target reads; lock transitions retire replies', async t => {
  const f = await fixture(t); await f.connect();
  let targeting = { locked_target: null, lock_state: 'idle' };
  f.ws.handlers.get_state = () => ({ ok: true, state: { id: 'ship_A', targeting }, mission_epoch: 1 });
  f.ws.session = { ship_id: 'ship_A', station: 'tactical', available_commands: ['get_target_solution', 'assess_damage'] };
  await f.stores.refreshCrewSession(); await settle();
  f.stores.selectedTargetId.set('nav_target');
  const reads = () => f.requests.filter(r => ['get_target_solution', 'assess_damage'].includes(r.cmd));
  assert.equal(await f.stores.pollLockedShipCommand('get_target_solution'), null);
  targeting = { locked_target: 'nav_target', lock_state: 'acquiring' }; await f.time.advance(200);
  assert.equal(await f.stores.pollLockedShipCommand('get_target_solution'), null);
  assert.equal(await f.stores.pollLockedShipCommand('assess_damage'), null);
  assert.equal(reads().length, 0);
  targeting = { locked_target: 'nav_target', lock_state: 'locked' }; await f.time.advance(200);
  assert.deepEqual(await f.stores.pollLockedShipCommand('get_target_solution'), { ok: true });
  const held = f.hold('get_target_solution'); const pending = f.stores.pollLockedShipCommand('get_target_solution');
  targeting = { locked_target: 'nav_target', lock_state: 'idle' }; await f.time.advance(200);
  assert.equal(read(f.stores.confirmedTargetLock).targetId, null);
  assert.equal(await f.stores.pollLockedShipCommand('get_target_solution'), null);
  // Even a rapid unlock/relock of the same contact retires the prior read.
  targeting = { locked_target: 'nav_target', lock_state: 'locked' }; await f.time.advance(200);
  held.resolve({ ok: true, confidence: 0.99 }); assert.equal(await pending, null);
  const oldTarget = f.hold('assess_damage'); const assessment = f.stores.pollLockedShipCommand('assess_damage');
  targeting = { locked_target: 'new_target', lock_state: 'locked' }; await f.time.advance(200);
  oldTarget.resolve({ ok: true, hull: 0.5 }); assert.equal(await assessment, null);
});


// Minimal dispatcher projection verified by tests/stations/test_station_commands.py.
const realCrewContract = JSON.parse(await readFile(new URL('./fixtures/crew-contract.json', import.meta.url), 'utf8'));

test('real dispatcher crew capability and nested envelope restore cards without stale fallback', async t => {
  const f = await fixture(t); await f.connect();
  {
    const contract = realCrewContract.assigned_ops;
    const role = contract.status.response.station;
    f.ws.handlers.my_status = () => contract.status;
    f.ws.handlers.crew_status = () => contract.crew;
    await f.stores.refreshCrewSession();
    assert.equal(read(f.stores.crewSession).station, role);
    assert.equal(f.stores.canPollShipCommand('crew_status'), true, role);
    const response = await f.stores.pollShipCommand('crew_status');
    const cards = f.stores.crewCardsFromResponse(response, [{ crewId: 'crew_1', station: 'engineering' }]);
    assert.equal(cards.length, 1, role);
    assert.equal(cards[0].name, 'Verified Engineer');
    assert.equal(cards[0].station, 'engineering');
    assert.equal(cards[0].fatigue, 0.25);
    assert.equal(cards[0].stress, 0.1);
    assert(cards[0].skills.engineering > 0);
    assert.deepEqual(f.stores.crewCardsFromResponse(null, cards), [], 'skipped reads clear old roster hints');
    f.ws.handlers.crew_status = () => ({ ok: false, message: 'Crew system not available', response: contract.crew.response });
    assert.deepEqual(f.stores.crewCardsFromResponse(await f.stores.pollShipCommand('crew_status'), cards), []);
    assert.deepEqual(f.stores.crewCardsFromResponse(f.ws.handlers.crew_status(), cards), [], 'rejected envelopes cannot provide display data');
    const held = f.hold('crew_status'); const pending = f.stores.pollShipCommand('crew_status');
    f.ws.emit('mission_changed', {}); await settle();
    held.resolve(contract.crew);
    assert.deepEqual(f.stores.crewCardsFromResponse(await pending, cards), [], 'retired crew replies clear cards');
  }
  // A server-authorized assignment without a station still fails the UI gate;
  // missing assignment or crew support never enables the background read.
  for (const name of ['assigned_unclaimed', 'unassigned', 'manager_unavailable']) {
    const contract = realCrewContract[name];
    f.ws.handlers.my_status = () => contract.status;
    f.ws.handlers.crew_status = () => contract.crew;
    await f.stores.refreshCrewSession();
    assert.equal(await f.stores.pollShipCommand('crew_status'), null, name);
  }
  f.ws.handlers.my_status = () => realCrewContract.assigned_ops.status;
  f.ws.handlers.crew_status = () => realCrewContract.assigned_ops.crew;
  await f.stores.refreshCrewSession();
  assert.equal(f.stores.crewCardsFromResponse(await f.stores.pollShipCommand('crew_status'))[0].name,
    'Verified Engineer', 'a refreshed valid authority resumes crew cards');
});
