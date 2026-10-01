const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { CrewTrace, redact, sharedPhysical, assertDenied } = require("../gui_crew_smoke");
const { assertPortsFree, stopGuiStack, redactStackLine, prepareEvidenceDirectory, parseArgs } = require("../gui_smoke_check");

const sent = (id, cmd = "set_thrust", args = {}) => JSON.stringify({ cmd, _request_id: id, ...args });
const received = (id, data = {}) => JSON.stringify({ type: "response", data: { ok: true, _request_id: id, ...data } });

test("native reply correlation isolates client and socket generations despite reused request IDs", () => {
  const trace = new CrewTrace();
  trace.record("helm", 1, "sent", sent(5, "set_thrust", { thrust: .2 }));
  trace.record("engineering", 1, "sent", sent(5, "set_thrust", { thrust: .2 }));
  trace.record("engineering", 1, "received", received(5, { ok: false, error: "Permission denied" }));
  const first = trace.request("helm", 0, "set_thrust", { thrust: .2 });
  assert.equal(trace.response(first), undefined);
  trace.record("helm", 2, "sent", sent(5, "set_thrust", { thrust: .2 }));
  const reconnect = trace.request("helm", 3, "set_thrust", { thrust: .2 });
  trace.record("helm", 1, "received", received(5, { marker: "retired socket" }));
  assert.equal(trace.response(reconnect), undefined);
  trace.record("helm", 2, "received", received(5, { marker: "current socket" }));
  assert.equal(trace.response(reconnect).marker, "current socket");
  assert.equal(trace.response(first).marker, "retired socket");
});

test("a previous thrust command cannot satisfy a new cutoff action", () => {
  const trace = new CrewTrace();
  trace.record("helm", 1, "sent", sent(1, "set_thrust", { thrust: 0 }));
  trace.record("helm", 1, "received", received(1));
  const cursor = trace.entries.length;
  trace.record("helm", 1, "sent", sent(2, "get_state", { full: true }));
  assert.equal(trace.request("helm", cursor, "set_thrust", { thrust: 0 }), undefined);
  trace.record("helm", 1, "sent", sent(3, "set_thrust", { thrust: .2 }));
  assert.equal(trace.request("helm", cursor, "set_thrust", { thrust: 0 }), undefined);
});

test("actual Playwright Node frame events decode their string or Buffer payload", () => {
  const trace = new CrewTrace();
  trace.record("helm", 1, "sent", { payload: sent(1) });
  trace.record("helm", 1, "received", { payload: Buffer.from(received(1)) });
  assert.equal(trace.response(trace.request("helm", 0, "set_thrust", {})).ok, true);
});

test("unknown commands and malformed/accepted responses cannot pass permission probes", () => {
  assertDenied({ ok: false, error: "Permission denied: Engineering cannot set_thrust" });
  for (const response of [{}, { ok: true }, { ok: false, error: "Unknown command" }, { ok: false, error: "missing ship" }]) {
    assert.throws(() => assertDenied(response));
  }
  assertDenied({ ok: false, error: "Station helm is controlled by Player_client_1" }, /claimed|occupied|controlled by/i);
  assert.throws(() => assertDenied({ ok: false, error: "Already controlling engineering. Release it first." }, /claimed|occupied|controlled by/i));
});

const physical = () => ({ ok: true, t: 12, mission_epoch: 3, state: { id: "player", position: { x: 0, y: 0, z: 0 },
  velocity: { x: 0, y: 0, z: 0 }, fuel: { level: 50 }, hull_integrity: 150, max_hull_integrity: 150, throttle: 0, reactor_output: .3 } });

test("shared-state evidence rejects missing telemetry or a different physical ship", () => {
  const baseline = physical();
  assert.deepEqual(sharedPhysical(baseline), sharedPhysical({ ...baseline, stationOnly: "ignored" }));
  for (const mutate of [r => delete r.t, r => delete r.mission_epoch, r => delete r.state.fuel,
    r => { r.state.id = "another_ship"; }, r => { r.state.velocity = null; }, r => { r.ok = false; }]) {
    const response = physical(); mutate(response); assert.throws(() => sharedPhysical(response));
  }
  const different = physical(); different.state.throttle = .2;
  assert.notDeepEqual(sharedPhysical(baseline), sharedPhysical(different));
});

test("captured evidence excludes auth traffic and recursively removes credentials", () => {
  const trace = new CrewTrace();
  trace.record("helm", 1, "sent", sent(1, "rcon_auth", { password: "private" }));
  trace.record("helm", 1, "received", received(1, { token: "private" }));
  trace.record("helm", 1, "sent", JSON.stringify({ type: "auth", code: "private" }));
  assert.equal(trace.entries.length, 0);
  const safe = redact({ physics: 4, nested: [{ password: "private", access_token: "private", game_code: "private" }] });
  assert.equal(safe.physics, 4); assert.ok(!JSON.stringify(safe).includes("private"));
  assert.equal(redactStackLine("[ready] RCON password: private"), "[startup credential line omitted]");
  assert.equal(redactStackLine("[ready] GUI: http://localhost:3100/"), "[ready] GUI: http://localhost:3100/");
});

test("occupied port refusal leaves the pre-existing listener alive", async () => {
  const occupied = net.createServer();
  await new Promise(resolve => occupied.listen(0, "127.0.0.1", resolve));
  try {
    await assert.rejects(assertPortsFree([occupied.address().port]), /will not attach to or stop an existing stack/);
    assert.equal(occupied.listening, true);
  } finally { await new Promise(resolve => occupied.close(resolve)); }
});

test("existing evidence is preserved rather than mixing successive runs", async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), "flaxos-crew-evidence-test-"));
  const directory = path.join(temporary, "result");
  try {
    await prepareEvidenceDirectory(directory);
    await fs.writeFile(path.join(directory, "old-result.json"), "retained original run");
    await assert.rejects(prepareEvidenceDirectory(directory), /already exists/);
    assert.equal(await fs.readFile(path.join(directory, "old-result.json"), "utf8"), "retained original run");
  } finally { await fs.rm(temporary, { recursive: true, force: true }); }
});

test("owned cleanup is idempotent and removes a descendant that ignores SIGTERM", { skip: process.platform === "win32" }, async () => {
  const descendantScript = "process.on('SIGTERM',()=>{});const net=require('net');const s=net.createServer();s.listen(0,'127.0.0.1',()=>console.log(s.address().port));";
  const parentScript = "const {spawn}=require('child_process');const c=spawn(process.execPath,['-e'," + JSON.stringify(descendantScript) + "],{stdio:['ignore','pipe','ignore']});c.stdout.once('data',d=>process.stdout.write(d));setInterval(()=>{},1000);";
  const child = spawn(process.execPath, ["-e", parentScript], { detached: true, stdio: ["ignore", "pipe", "pipe"] });
  child.ownedGroup = true;
  try {
    const [raw] = await once(child.stdout, "data"); const port = Number(raw.toString());
    assert.ok(port > 0);
    child.ownedPorts = [port];
    await stopGuiStack(child); await stopGuiStack(child);
    await assertPortsFree([port]);
    assert.equal(child.signalCode, "SIGTERM");
  } finally { await stopGuiStack(child); }
});

test("crew invocation preserves explicit owned-stack and evidence options", () => {
  const options = parseArgs(["--crew", "--start-stack", "--python", "/tmp/test-python", "--evidence-dir", "/tmp/test-evidence"]);
  assert.equal(options.crew, true); assert.equal(options.autoStart, true);
  assert.equal(options.python, "/tmp/test-python"); assert.equal(options.evidenceDir, "/tmp/test-evidence");
  assert.equal(parseArgs([]).crew, false);
});
