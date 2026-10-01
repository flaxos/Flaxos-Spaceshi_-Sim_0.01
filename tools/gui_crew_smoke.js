// Bounded Svelte -> real WS bridge -> station server smoke, using normal UI actions.
// No routeWebSocket, response replacement, credentials, or gameplay changes.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const SHIP = "player";
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const unwrap = response => response.response ?? response.data ?? response;

function redact(value) {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    /^(?:password|.*token|.*secret|game_code|code)$/i.test(key) ? "[omitted]" : redact(item)]));
}

class CrewTrace {
  constructor() { this.entries = []; this.requests = new Map(); }
  record(client, socket, direction, raw) {
    const frame = JSON.parse((raw.payload ?? raw).toString());
    let command;
    if (direction === "sent") {
      command = frame.cmd;
      if (!command || command.startsWith("rcon_") || command === "_ping") return;
      this.requests.set(`${client}:${socket}:${frame._request_id}`, command);
    } else {
      if (!["response", "error"].includes(frame.type)) return;
      command = this.requests.get(`${client}:${socket}:${frame.data?._request_id}`);
      if (!command) return;
    }
    this.entries.push({ client, socket, direction, command, wallMs: Date.now(), frame: redact(frame) });
  }
  request(client, start, command, args) {
    return this.entries.slice(start).find(row => row.client === client && row.direction === "sent" && row.command === command &&
      Object.entries(args).every(([key, value]) => row.frame[key] === value));
  }
  response(request) {
    return this.entries.find(row => row.client === request.client && row.socket === request.socket && row.direction === "received" &&
      row.frame.data?._request_id === request.frame._request_id)?.frame.data;
  }
}

async function until(check, description, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  do { const value = await check(); if (value) return value; await delay(50); } while (Date.now() < deadline);
  throw new Error(`Timed out: ${description}`);
}

function assertAccepted(response) { assert.equal(response?.ok, true, JSON.stringify(response)); }
function assertDenied(response, pattern = /permission denied/i) {
  assert.equal(response?.ok, false, JSON.stringify(response));
  assert.match(String(response.error ?? response.message ?? ""), pattern);
}

function sharedPhysical(response) {
  assertAccepted(response);
  const result = { t: response.t, mission_epoch: response.mission_epoch };
  assert.ok(Number.isFinite(result.t) && Number.isFinite(result.mission_epoch), "Missing actual clock/epoch");
  for (const field of ["id", "position", "velocity", "fuel", "hull_integrity", "max_hull_integrity", "throttle", "reactor_output"]) {
    assert.ok(Object.hasOwn(response.state ?? {}, field) && response.state[field] != null, `Missing actual shared field ${field}`);
    result[field] = response.state[field];
  }
  assert.equal(result.id, SHIP);
  return result;
}

async function runCrewSmoke({ browser, url, evidenceDir, repoRoot }) {
  const trace = new CrewTrace(), errors = [], checks = [], clients = [], snapshots = [];
  const result = { status: "failed", sha: execFileSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).trim(),
    dirtyCheckout: !!execFileSync("git", ["status", "--porcelain"], { cwd: repoRoot, encoding: "utf8" }).trim(),
    scenario: "07_docking_test", independentContexts: 2, actualSvelteWsTcp: true, transportMocked: false,
    completedDockingFlight: false, humanUAT: "pending", checks, snapshots };
  if (evidenceDir) await fs.mkdir(evidenceDir, { recursive: true, mode: 0o700 });
  const screenshot = async (page, name) => { if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, `${name}.png`) }); };
  async function invoke(client, command, args, action) {
    const start = trace.entries.length;
    await action();
    const request = await until(() => trace.request(client.label, start, command, args), `${client.label} native ${command} request`);
    return until(() => trace.response(request), `${client.label} correlated ${command} response`);
  }
  async function consoleCommand(client, command, args = {}) {
    const page = client.page;
    await page.getByRole("tab", { name: "0 MISSION", exact: true }).click();
    await page.getByRole("tab", { name: "CONSOLE", exact: true }).click();
    return invoke(client, command, args, async () => {
      await page.getByPlaceholder("command [args...]", { exact: true }).fill(`${command} ${JSON.stringify(args)}`);
      await page.getByPlaceholder("command [args...]", { exact: true }).press("Enter");
    });
  }
  async function accepted(client, command, args) { const response = await consoleCommand(client, command, args); assertAccepted(response); return response; }
  const state = client => accepted(client, "get_state", { ship: SHIP, full: true });
  const session = async client => unwrap(await accepted(client, "my_status", {}));
  async function release(client) {
    if (!(await client.page.locator(".station-panel").isVisible())) await client.page.locator(".claimed-badge").click();
    assertAccepted(await invoke(client, "release_station", {}, () => client.page.getByRole("button", { name: "Release Station", exact: true }).click()));
    await client.page.locator(".claimed-badge").waitFor({ state: "detached" });
  }
  async function claim(client, station) {
    if (!(await client.page.locator(".station-panel").isVisible())) await client.page.locator(".expand-btn").click();
    assertAccepted(await invoke(client, "claim_station", { ship: SHIP, station }, () =>
      client.page.locator(".station-btn").filter({ has: client.page.locator(".station-btn-label", { hasText: new RegExp(`^${station.toUpperCase()}$`) }) }).click()));
    await client.page.locator(".claimed-badge", { hasText: station.toUpperCase() }).waitFor();
  }
  async function manualThrust(client, percent) {
    await client.page.getByRole("tab", { name: "1 HELM", exact: true }).click();
    await client.page.getByRole("button", { name: "MANUAL", exact: true }).click();
    const input = client.page.locator(".manual-flight-panel .throttle input[type=number]");
    const response = await invoke(client, "set_thrust", { ship: SHIP, thrust: percent / 100 }, async () => { await input.fill(String(percent)); await input.press("Tab"); });
    assertAccepted(response);
    await until(async () => (await state(client)).state.throttle === percent / 100, `actual thrust ${percent}%`);
  }
  try {
    for (const label of ["helm", "engineering"]) {
      const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
      // Transparent NativeSocket subclass allows one real close; no routing or mocks.
      await context.addInitScript(() => {
        const NativeSocket = window.WebSocket;
        window.__crewSmokeSockets = [];
        window.WebSocket = class extends NativeSocket { constructor(...args) { super(...args); window.__crewSmokeSockets.push(this); } };
      });
      const page = await context.newPage(); page.setDefaultTimeout(10000);
      const client = { label, context, page }; clients.push(client);
      let socket = 0;
      page.on("pageerror", error => errors.push({ client: label, error: String(error) }));
      page.on("websocket", ws => {
        const generation = ++socket;
        for (const [event, direction] of [["framesent", "sent"], ["framereceived", "received"]]) {
          ws.on(event, raw => { try { trace.record(label, generation, direction, raw); } catch (error) { errors.push({ client: label, error: String(error) }); } });
        }
      });
    }
    const [a, b] = clients;
    await a.page.goto(url);
    await a.page.getByRole("button", { name: "Connection status: connected", exact: false }).waitFor();
    await a.page.getByRole("button", { name: "NEW GAME", exact: true }).click();
    const mission = a.page.locator(".mission-card").filter({ has: a.page.locator(".card-name", { hasText: /^Docking Test: Short Range Approach$/ }) });
    assertAccepted(await invoke(a, "load_scenario", { scenario: "07_docking_test" }, () => mission.getByRole("button", { name: "LAUNCH", exact: true }).click()));
    await a.page.locator(".claimed-badge", { hasText: "CAPTAIN" }).waitFor();
    await accepted(a, "pause", { on: true });
    await accepted(a, "set_time_scale", { time_scale: 1 });
    await accepted(a, "set_reactor_output", { ship: SHIP, output: 30 });
    await accepted(a, "set_thrust", { ship: SHIP, thrust: 0 });
    await accepted(a, "pause", { on: false });
    await release(a); await claim(a, "helm");

    await b.page.goto(url);
    await b.page.getByRole("button", { name: "Connection status: connected", exact: false }).waitFor();
    await b.page.getByRole("button", { name: "JOIN GAME", exact: true }).click();
    const ship = b.page.locator(".ship-card").filter({ has: b.page.locator(".ship-id", { hasText: /^player$/ }) });
    assertAccepted(await invoke(b, "claim_station", { ship: SHIP, station: "engineering" }, () =>
      ship.locator(".station-slot.vacant").filter({ has: b.page.locator(".st-name", { hasText: /^ENGINEERING$/ }) }).click()));
    await b.page.locator(".claimed-badge", { hasText: "ENGINEERING" }).waitFor();
    const firstA = await session(a), firstB = await session(b);
    assert.equal(firstA.ship_id, SHIP); assert.equal(firstB.ship_id, SHIP);
    assert.equal(firstA.station, "helm"); assert.equal(firstB.station, "engineering");
    assert.notEqual(firstA.client_id, firstB.client_id);
    assert.equal(await a.page.getByRole("tab", { name: "3 ENGINEERING", exact: true }).getAttribute("aria-disabled"), "true");
    assert.equal(await b.page.getByRole("tab", { name: "1 HELM", exact: true }).getAttribute("aria-disabled"), "true");
    checks.push("Separate real sessions hold complementary Helm and Engineering roles");

    await release(b);
    assertDenied(await consoleCommand(b, "claim_station", { ship: SHIP, station: "helm" }), /claimed|occupied|controlled by/i);
    assert.equal((await session(b)).station, null); assert.equal((await session(a)).station, "helm");
    await claim(b, "engineering");
    assertDenied(await consoleCommand(b, "set_thrust", { ship: SHIP, thrust: .25 }));
    await b.page.locator(".command-error", { hasText: "set_thrust" }).waitFor();
    assertDenied(await consoleCommand(a, "set_reactor_output", { ship: SHIP, output: 50 }));
    await a.page.locator(".command-error", { hasText: "set_reactor_output" }).waitFor();
    await accepted(b, "set_reactor_output", { ship: SHIP, output: 30 });
    checks.push("Occupied Helm claim denied with peer claim intact; explicit Engineering rejoin; server denies cross-station commands visibly");
    await screenshot(b.page, "complementary-permission-denial");

    const disconnectedAt = trace.entries.length;
    await a.page.evaluate(() => window.__crewSmokeSockets.at(-1).close(1000, "Crew smoke explicit reconnect"));
    await a.page.locator(".crew-notice").waitFor();
    const rejoin = a.page.locator(".crew-notice").getByRole("button", { name: "Rejoin crew", exact: true });
    await until(async () => !(await rejoin.isDisabled()), "reconnected observer offers explicit rejoin");
    await delay(1500);
    const observer = await session(a);
    assert.equal(observer.ship_id, null); assert.equal(observer.station, null);
    assert.notEqual(observer.client_id, firstA.client_id);
    assert.equal((await session(b)).client_id, firstB.client_id);
    assert.equal((await session(b)).station, "engineering");
    const status = unwrap(await accepted(b, "station_status", { ship: SHIP }));
    assert.equal(status.stations.find(row => row.station === "helm").claimed, false);
    assert.equal(status.stations.find(row => row.station === "engineering").claimed, true);
    assert.equal(trace.entries.slice(disconnectedAt).filter(row => row.client === "helm" && row.direction === "sent" && ["assign_ship", "claim_station"].includes(row.command)).length, 0);
    assertDenied(await consoleCommand(a, "set_thrust", { ship: SHIP, thrust: .25 }), /not assigned|no station/i);
    await screenshot(a.page, "reconnected-observer-before-explicit-rejoin");
    await rejoin.click();
    const rejoinShip = a.page.locator(".ship-card").filter({ has: a.page.locator(".ship-id", { hasText: /^player$/ }) });
    assertAccepted(await invoke(a, "claim_station", { ship: SHIP, station: "helm" }, () =>
      rejoinShip.locator(".station-slot.vacant").filter({ has: a.page.locator(".st-name", { hasText: /^HELM$/ }) }).click()));
    await a.page.locator(".claimed-badge", { hasText: "HELM" }).waitFor();
    await a.page.locator(".crew-notice").waitFor({ state: "detached" });
    assert.equal((await session(a)).station, "helm"); assert.equal((await session(b)).station, "engineering");
    checks.push("Real socket close frees Helm; reconnect remains observer until explicit UI rejoin; peer Engineering survives");

    await manualThrust(a, 20);
    const burning = await state(a); assert.equal(burning.state.throttle, .2);
    snapshots.push({ phase: "manual 20% after explicit rejoin", response: burning });
    await manualThrust(a, 0);
    const cutoff = await state(a); assert.equal(cutoff.state.throttle, 0);
    snapshots.push({ phase: "explicit manual zero command", response: cutoff });
    await a.page.getByRole("tab", { name: "1 HELM", exact: true }).click();
    await a.page.locator(".manual-flight-panel .throttle .row-head strong", { hasText: /^0%$/ }).waitFor();
    await screenshot(a.page, "explicit-manual-thrust-cutoff");
    checks.push("Rejoined Helm sends accepted 20% and explicit 0% through Manual Flight; actual telemetry confirms both");

    await release(a); await claim(a, "captain"); await accepted(a, "pause", { on: true });
    await release(a); await claim(a, "helm");
    const finalA = await state(a), finalB = await state(b);
    assert.deepEqual(sharedPhysical(finalA), sharedPhysical(finalB));
    assert.equal(finalA.state.throttle, 0); assert.equal(finalB.state.engineering.fuel_burn_rate, 0);
    snapshots.push({ phase: "same paused physical ship at both stations", helm: finalA, engineering: finalB });
    result.finalSessions = { helm: await session(a), engineering: await session(b) };
    assert.equal(result.finalSessions.helm.station, "helm"); assert.equal(result.finalSessions.engineering.client_id, firstB.client_id);
    assert.equal(result.finalSessions.engineering.station, "engineering");
    assert.deepEqual(errors, []);
    checks.push("Both stations report identical paused clock/epoch, position, velocity, fuel, hull, reactor setting and zero actual throttle");
    result.status = "passed";
    return result;
  } catch (error) { result.error = error.message; throw error; }
  finally {
    result.pageErrors = errors;
    if (evidenceDir) {
      await fs.writeFile(path.join(evidenceDir, "crew-smoke-result.json"), JSON.stringify(result, null, 2), { mode: 0o600 });
      await fs.writeFile(path.join(evidenceDir, "crew-smoke-native-traffic.json"), JSON.stringify(trace.entries, null, 2), { mode: 0o600 });
    }
    for (const client of clients) await client.context.close();
  }
}

module.exports = { CrewTrace, redact, sharedPhysical, assertDenied, runCrewSmoke };
