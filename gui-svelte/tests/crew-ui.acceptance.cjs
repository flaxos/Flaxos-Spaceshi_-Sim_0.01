// Optional built-UI regression: run with the repository's installed Playwright
// and FLAXOS_CHROMIUM (defaults to /usr/bin/chromium). All WS traffic is mocked.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const os = require('node:os');

(async () => {
  const frontend = path.resolve(__dirname, '..');
  const dir = process.env.FLAXOS_UI_EVIDENCE || path.join(os.tmpdir(), 'flaxos-crew-ui-evidence');
  const buildDir = await fs.mkdtemp(path.join(os.tmpdir(), 'flaxos-built-ui-'));
  await fs.mkdir(dir, { recursive: true });
  const { build } = await import('vite');
  await build({ root: frontend, configFile: path.join(frontend, 'vite.config.ts'), logLevel: 'error', build: { outDir: buildDir } });
  const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' };
  const server = http.createServer(async (req, res) => {
    try {
      const file = path.join(buildDir, new URL(req.url, 'http://localhost').pathname === '/' ? 'index.html' : new URL(req.url, 'http://localhost').pathname);
      const body = await fs.readFile(file); res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream'); res.end(body);
    } catch { res.statusCode = 404; res.end('Not found'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: process.env.FLAXOS_CHROMIUM || '/usr/bin/chromium', headless: true, args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
    const requests = [], errors = [];
    let session = { ship_id: null, station: null }, epoch = 1, outcome = 'in_progress', route;
    await context.routeWebSocket(/.*/, ws => {
      route = ws;
      ws.onMessage(raw => {
        const msg = JSON.parse(raw.toString()); requests.push({ wall: Date.now(), ...msg });
        let data = { ok: true };
        if (msg.cmd === 'my_status') data.response = { client_id: 'client_ui', ...session };
        if (msg.cmd === 'list_ships') data.response = { ships: [{ id: 'player', name: 'CREW UI MOCK', class: 'corvette' }] };
        if (msg.cmd === 'station_status') data.response = { ship_id: 'player', stations: ['captain', 'helm', 'engineering'].map(station => ({ station, claimed: station === session.station, player: station === session.station ? 'Crew UI Mock' : null })) };
        if (msg.cmd === 'assign_ship') session.ship_id = msg.ship;
        if (msg.cmd === 'claim_station') session.station = msg.station;
        if (msg.cmd === 'release_station') session.station = null;
        if (msg.cmd === 'get_events') data.events = [];
        if (msg.cmd === 'get_state') data = { ok: true, t: 0, mission_epoch: epoch, active_scenario: '07_docking_test', state: session.ship_id && session.station ? { id: 'player', name: 'CREW UI MOCK', velocity: { x: 0, y: 0, z: 0 }, position: { x: 0, y: 0, z: 0 }, systems: {} } : undefined };
        if (msg.cmd === 'get_mission') data.mission = { available: true, mission_epoch: epoch, current_scenario_id: '07_docking_test', mission_status: outcome, name: 'UI ONLY DOCKING MOCK', failure_message: 'Controlled failure outcome' };
        if (msg.cmd === 'load_scenario') { epoch++; outcome = 'in_progress'; data.scenario = msg.scenario; }
        if (msg.cmd === 'set_throttle') data = { ok: false, error: 'Controlled station permission rejection' };
        if (msg.cmd === '_ping') { ws.send(JSON.stringify({ type: 'pong', data: { timestamp: msg.timestamp } })); return; }
        ws.send(JSON.stringify({ type: 'response', data: { ...data, _request_id: msg._request_id } }));
      });
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.getByRole('button', { name: /Connection status: connected/ }).waitFor();
    await page.getByRole('button', { name: 'JOIN GAME', exact: true }).click();
    await page.locator('.station-slot.vacant').filter({ has: page.locator('.st-name', { hasText: /^HELM$/ }) }).click();
    await page.locator('.claimed-badge', { hasText: 'HELM' }).waitFor();
    const helmTab = page.getByRole('tab', { name: '1 HELM', exact: true });
    assert.equal(await helmTab.getAttribute('aria-disabled'), 'false');
    await helmTab.click();
    assert.equal(await helmTab.getAttribute('aria-selected'), 'true');
    await page.screenshot({ path: path.join(dir, 'crew-ui-helm.png') });
    await page.locator('.claimed-badge').click();
    await page.getByRole('button', { name: 'Release Station', exact: true }).click();
    await page.locator('.claimed-badge').waitFor({ state: 'detached' });
    assert.equal(await helmTab.getAttribute('aria-disabled'), 'true');
    await page.locator('.station-btn').filter({ has: page.locator('.station-btn-label', { hasText: /^ENGINEERING$/ }) }).click();
    await page.locator('.claimed-badge', { hasText: 'ENGINEERING' }).waitFor();
    const engineerTab = page.getByRole('tab', { name: '3 ENGINEERING', exact: true });
    assert.equal(await engineerTab.getAttribute('aria-disabled'), 'false');
    assert.equal(await helmTab.getAttribute('aria-disabled'), 'true');
    await engineerTab.click();
    assert.equal(await engineerTab.getAttribute('aria-selected'), 'true');
    const beforeDisconnect = requests.length;
    session = { ship_id: null, station: null };
    await route.close({ code: 1012, reason: 'Controlled regression disconnect' });
    await page.locator('.crew-notice').waitFor();
    const rejoin = page.locator('.crew-notice').getByRole('button', { name: 'Rejoin crew', exact: true });
    await rejoin.waitFor();
    for (let i = 0; i < 60 && await rejoin.isDisabled(); i++) await page.waitForTimeout(50);
    assert.equal(await rejoin.isDisabled(), false);
    assert.equal(requests.slice(beforeDisconnect).filter(r => ['assign_ship', 'claim_station'].includes(r.cmd)).length, 0);
    await rejoin.click();
    await page.locator('.station-slot.vacant').filter({ has: page.locator('.st-name', { hasText: /^ENGINEERING$/ }) }).click();
    await page.locator('.crew-notice').waitFor({ state: 'detached' });
    await page.locator('.claimed-badge', { hasText: 'ENGINEERING' }).waitFor();
    outcome = 'failure';
    await page.getByRole('tab', { name: '0 MISSION', exact: true }).click();
    await page.locator('.post-title', { hasText: 'MISSION FAILED' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'REPLAY CURRENT MISSION', exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: 'NEXT MISSION', exact: true }).count(), 0);
    await page.screenshot({ path: path.join(dir, 'crew-ui-failure.png') });
    session.station = 'captain';
    await page.locator('.claimed-badge', { hasText: 'CAPTAIN' }).waitFor({ timeout: 5000 });
    await page.getByRole('tab', { name: '0 MISSION', exact: true }).click();
    await page.getByRole('button', { name: 'REPLAY CURRENT MISSION', exact: true }).click();
    await page.locator('.post-title').waitFor({ state: 'detached' });
    const replay = requests.filter(r => r.cmd === 'load_scenario').at(-1);
    assert.equal(replay.scenario, '07_docking_test'); assert.equal(replay.force, true);
    await page.getByRole('tab', { name: '0 MISSION', exact: true }).click();
    await page.getByRole('tab', { name: 'CONSOLE', exact: true }).click();
    await page.locator('.prompt-input').fill('set_throttle throttle=0.5');
    await page.locator('.prompt-input').press('Enter');
    await page.locator('.command-error', { hasText: 'Controlled station permission rejection' }).waitFor();
    assert.deepEqual(errors, []);
    const result = { status: 'passed', actualBuiltSvelte: true, allWebSocketsMocked: true,
      checks: ['Helm role enables Helm tab', 'Release disables old tabs', 'Engineering role enables Engineering tab', 'Reconnect sends no assign/claim before explicit rejoin', 'Rejoin opens usable lobby', 'Failure labels and captain-only forced current replay', 'Global rejection feedback'], replay, pageErrors: errors };
    await fs.writeFile(path.join(dir, 'crew-ui-results.json'), JSON.stringify(result, null, 2));
    await fs.writeFile(path.join(dir, 'crew-ui-network.json'), JSON.stringify(requests, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close(); await new Promise(resolve => server.close(resolve)); await fs.rm(buildDir, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exit(1); });
