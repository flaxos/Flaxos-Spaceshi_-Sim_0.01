import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(path.join(tmpdir(), 'flaxos-lobby-refresh-'));
after(() => rm(temporary, { recursive: true, force: true }));
const bundle = path.join(temporary, 'lobby.mjs');
await build({ entryPoints: [path.join(frontend, 'src/lib/lobbyRefresh.ts')], outfile: bundle,
  bundle: true, format: 'esm', platform: 'node' });
const { createLobbyRefresh } = await import(pathToFileURL(bundle));
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}

function fixture(t) {
  const real = { setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  let now = 0, sequence = 0;
  const timers = new Map(), requests = [], snapshots = [], loading = [], holds = new Map();
  globalThis.setTimeout = (fn, ms) => { const id = ++sequence; timers.set(id, { fn, due: now + ms }); return id; };
  globalThis.clearTimeout = id => timers.delete(id);
  t.after(() => Object.assign(globalThis, real));
  let owner = null, unavailable = 0;
  const replies = {
    list_ships: () => ({ ok: true, response: { ships: [{ id: 'ship_A' }, { id: 'ship_B' }] } }),
    station_status: args => ({ ok: true, response: { stations: [{ station: 'helm', claimed: !!owner, player: owner }] } }),
  };
  const loop = createLobbyRefresh({
    send(cmd, args) {
      requests.push({ cmd, args, time: now });
      const key = cmd === 'station_status' ? `${cmd}:${args.ship}` : cmd;
      if (holds.has(key)) { const hold = holds.get(key); holds.delete(key); return hold.promise; }
      return Promise.resolve(replies[cmd](args));
    },
    onSnapshot: snapshot => snapshots.push(snapshot),
    onUnavailable: () => { unavailable++; },
    onLoading: value => loading.push(value),
  });
  t.after(() => loop.destroy());
  return {
    loop, requests, snapshots, loading, timers, replies,
    get unavailable() { return unavailable; },
    set owner(value) { owner = value; },
    hold(key) { const d = deferred(); holds.set(key, d); return d; },
    async advance(ms) {
      const target = now + ms;
      while (true) {
        const next = [...timers].sort((a, b) => a[1].due - b[1].due)[0];
        if (!next || next[1].due > target) break;
        now = next[1].due; timers.delete(next[0]); next[1].fn(); await settle();
      }
      now = target; await settle();
    },
  };
}

test('observer lobby follows peer claim, handover and release with only existing reads', async t => {
  const f = fixture(t);
  f.loop.setActive(true); await settle();
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].claimed, false);
  f.owner = 'Helm peer'; await f.advance(2000);
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].player, 'Helm peer');
  f.owner = 'Successor'; await f.advance(2000);
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].player, 'Successor');
  f.owner = null; await f.advance(2000);
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].claimed, false);
  assert.deepEqual([...new Set(f.requests.map(r => r.cmd))], ['list_ships', 'station_status']);
  assert.equal(f.timers.size, 1);
});

test('manual refresh coalesces with a pending automatic batch and resets one timer', async t => {
  const f = fixture(t);
  const held = f.hold('station_status:ship_A');
  f.loop.setActive(true); await settle();
  const manual = f.loop.refresh();
  assert.strictEqual(f.loop.refresh(), manual);
  await f.advance(30000);
  assert.equal(f.requests.length, 3);
  assert.equal(f.snapshots.length, 0, 'no partial fleet is published');
  assert.equal(f.timers.size, 0, 'slow requests do not accumulate polls');
  held.resolve({ ok: true, response: { stations: [{ station: 'helm', claimed: true, player: 'Latest' }] } });
  await manual;
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].player, 'Latest');
  assert.equal(f.timers.size, 1);
  await f.advance(1000);
  await f.loop.refresh();
  assert.equal(f.timers.size, 1);
  const count = f.requests.length;
  await f.advance(1999); assert.equal(f.requests.length, count);
  await f.advance(1); assert.equal(f.requests.length, count + 3);
});

test('disconnect retires an old occupancy response and reconnect refreshes without reclaim', async t => {
  const f = fixture(t);
  const old = f.hold('station_status:ship_A');
  f.loop.setActive(true); await settle();
  f.loop.setActive(false);
  await f.advance(10000);
  assert.equal(f.timers.size, 0); assert.equal(f.snapshots.length, 0);
  f.owner = 'New peer'; f.loop.setActive(true); await settle();
  const fresh = f.snapshots.at(-1);
  const loadingCount = f.loading.length;
  old.resolve({ ok: true, response: { stations: [{ station: 'helm', claimed: false }] } });
  await settle();
  assert.strictEqual(f.snapshots.at(-1), fresh);
  assert.equal(f.loading.length, loadingCount, 'retired finally cannot alter current loading');
  assert.equal(f.timers.size, 1);
  assert.equal(f.requests.some(r => ['assign_ship', 'claim_station', 'register_client'].includes(r.cmd)), false);
  await f.advance(2000);
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].player, 'New peer');
});

for (const stage of ['list_ships', 'station_status:ship_A']) {
  test(`leaving lobby/hidden view/hidden document retires ${stage} without further work`, async t => {
    const f = fixture(t);
    const old = f.hold(stage);
    f.loop.setActive(true); await settle();
    f.loop.setActive(false);
    const count = f.requests.length;
    old.resolve(stage === 'list_ships' ? { ships: [{ id: 'retired' }] } : { ok: true });
    await settle(); await f.advance(30000);
    assert.equal(f.requests.length, count);
    assert.equal(f.snapshots.length, 0);
    assert.equal(f.unavailable, 0, 'a retired response cannot display an error');
    assert.equal(f.timers.size, 0);
    f.loop.setActive(true); await settle();
    assert.equal(f.snapshots.length, 1, 'returning to the visible lobby refreshes immediately');
    assert.equal(f.timers.size, 1);
  });
}

test('unmount cancels timers and prevents held replies, activation or manual refresh from reviving polling', async t => {
  const f = fixture(t);
  f.loop.setActive(true); await settle();
  const old = f.hold('list_ships'); await f.advance(2000);
  const count = f.requests.length, snapshots = f.snapshots.length;
  f.loop.destroy();
  old.reject(new Error('Old connection failed')); await settle();
  f.loop.setActive(true); f.loop.restart(); await f.loop.refresh(); await f.advance(30000);
  assert.equal(f.requests.length, count); assert.equal(f.snapshots.length, snapshots);
  assert.equal(f.unavailable, 0); assert.equal(f.timers.size, 0);
});

test('mission reset and late failed responses cannot replace a newer fleet or duplicate its loop', async t => {
  const f = fixture(t);
  const old = f.hold('list_ships');
  f.loop.setActive(true); await settle();
  f.replies.list_ships = () => ({ data: { ships: [{ id: 'new_ship' }] } });
  f.loop.restart(); await settle();
  assert.equal(f.snapshots.at(-1).ships[0].id, 'new_ship');
  old.reject(new Error('Retired response')); await settle();
  assert.equal(f.unavailable, 0); assert.equal(f.timers.size, 1);
  await f.advance(2000);
  assert.equal(f.requests.filter(r => r.cmd === 'station_status' && r.args.ship === 'ship_A').length, 0);
});

test('a rejected ship read waits for every pending occupancy request before retrying', async t => {
  const f = fixture(t);
  const slow = f.hold('station_status:ship_B');
  f.replies.station_status = () => ({ ok: false, error: 'Read unavailable' });
  f.loop.setActive(true); await settle(); await f.advance(10000);
  assert.equal(f.requests.length, 3); assert.equal(f.timers.size, 0);
  slow.resolve({ stations: [{ station: 'helm', claimed: false }] }); await settle();
  assert.equal(f.unavailable, 1); assert.equal(f.snapshots.length, 0); assert.equal(f.timers.size, 1);
  f.replies.station_status = () => ({ response: { stations: [{ station: 'helm', claimed: true, player: 'Recovered' }] } });
  await f.advance(2000);
  assert.equal(f.snapshots.at(-1).ships[0].stations[0].player, 'Recovered');
});

test('rejected or malformed occupancy never publishes a vacant station; an empty fleet is valid', async t => {
  const f = fixture(t);
  for (const reply of [{ ok: false }, { success: false, response: { stations: [{ station: 'helm', claimed: false }] } },
    { response: { ok: false, stations: [{ station: 'helm', claimed: false }] } }, { response: {} },
    { response: { stations: [{ station: 'helm' }] } }, { response: { stations: 'bad' } }]) {
    f.replies.station_status = () => reply;
    if (!f.requests.length) f.loop.setActive(true);
    else await f.loop.refresh();
    await settle();
    assert.equal(f.snapshots.length, 0);
  }
  assert.equal(f.unavailable, 6);
  f.replies.list_ships = () => ({ response: { ships: [] } });
  await f.loop.refresh();
  assert.deepEqual(f.snapshots.at(-1).ships, []);
});
