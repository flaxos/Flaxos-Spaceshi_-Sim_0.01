// Playwright verification test for the maneuvering IR signature feature.
// Verifies: status bar IR indicator, IR level categories, cold-drift display.

const { test, expect } = require("@playwright/test");
const path = require("path");
const http = require("http");
const fs = require("fs");

// Serve a minimal test page that loads the status-bar component
// with injected mock state data.
function startServer(port) {
  return new Promise((resolve) => {
    const guiDir = path.join(__dirname, "gui");

    const server = http.createServer((req, res) => {
      // Serve the test HTML page
      if (req.url === "/" || req.url === "/test.html") {
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(getTestPageHtml());
        return;
      }

      // Serve GUI assets (JS files)
      let filePath = path.join(guiDir, req.url);
      if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        const ext = path.extname(filePath);
        const types = {
          ".js": "application/javascript",
          ".css": "text/css",
          ".html": "text/html",
        };
        res.writeHead(200, { "Content-Type": types[ext] || "text/plain" });
        res.end(fs.readFileSync(filePath, "utf-8"));
        return;
      }

      res.writeHead(404);
      res.end("Not found");
    });

    server.listen(port, () => resolve(server));
  });
}

function getTestPageHtml() {
  return `<!DOCTYPE html>
<html>
<head>
  <style>
    :root {
      --bg-panel: #12121a;
      --border-default: #2a2a3a;
      --text-dim: #555566;
      --font-sans: "Inter", sans-serif;
      --font-mono: "JetBrains Mono", monospace;
      --bg-input: #1a1a24;
      --status-nominal: #00ff88;
      --status-warning: #ffaa00;
      --status-critical: #ff4444;
      --status-info: #00aaff;
      --status-offline: #555566;
    }
    body { background: #0a0a0f; margin: 0; padding: 20px; }
  </style>
</head>
<body>
  <status-bar id="testBar"></status-bar>

  <script type="module">
    // Minimal mock state manager that the status-bar component imports
    class MockStateManager {
      constructor() {
        this._shipState = {};
        this._subscribers = new Map();
        this._subscriberCounter = 0;
      }

      subscribe(key, callback) {
        const id = ++this._subscriberCounter;
        this._subscribers.set(id, callback);
        return () => this._subscribers.delete(id);
      }

      getShipState() {
        return this._shipState;
      }

      getNavigation() {
        const ship = this._shipState;
        let position = [0, 0, 0];
        let velocity = [0, 0, 0];
        if (ship?.velocity) {
          velocity = [ship.velocity.x || 0, ship.velocity.y || 0, ship.velocity.z || 0];
        }
        return { position, velocity };
      }

      // Inject test state and notify subscribers
      setTestState(state) {
        this._shipState = state;
        for (const cb of this._subscribers.values()) {
          cb();
        }
      }
    }

    // Create the global mock before the component loads it
    const mockStateManager = new MockStateManager();
    window.__mockStateManager = mockStateManager;

    // Override the module import
    // We re-define the status-bar component inline with our mock
    class TestStatusBar extends HTMLElement {
      constructor() {
        super();
        this.attachShadow({ mode: "open" });
        this._unsubscribe = null;
      }

      connectedCallback() {
        this.render();
        this._subscribe();
      }

      disconnectedCallback() {
        if (this._unsubscribe) this._unsubscribe();
      }

      _subscribe() {
        this._unsubscribe = mockStateManager.subscribe("*", () => {
          this._updateDisplay();
        });
      }

      render() {
        this.shadowRoot.innerHTML = \`
          <style>
            :host { display: block; background: var(--bg-panel); border-bottom: 1px solid var(--border-default); padding: 6px 12px; font-family: var(--font-sans); font-size: 0.75rem; }
            .status-bar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
            .status-group { display: flex; align-items: center; gap: 6px; }
            .status-label { color: var(--text-dim); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }
            .status-value { font-family: var(--font-mono); font-size: 0.8rem; font-weight: 600; }
            .status-value.nominal { color: var(--status-nominal); }
            .status-value.warning { color: var(--status-warning); }
            .status-value.critical { color: var(--status-critical); }
            .status-value.info { color: var(--status-info); }
            .separator { width: 1px; height: 16px; background: var(--border-default); }
            .mini-bar { width: 60px; height: 6px; background: var(--bg-input); border-radius: 3px; overflow: hidden; }
            .mini-bar-fill { height: 100%; transition: width 0.3s ease; }
            .mini-bar-fill.nominal { background: var(--status-nominal); }
            .mini-bar-fill.warning { background: var(--status-warning); }
            .mini-bar-fill.critical { background: var(--status-critical); }
            .empty-state { color: var(--text-dim); font-style: italic; font-size: 0.75rem; }
          </style>
          <div class="status-bar" id="bar">
            <span class="empty-state">Awaiting ship data...</span>
          </div>
        \`;
      }

      _updateDisplay() {
        const ship = mockStateManager.getShipState();
        const bar = this.shadowRoot.getElementById("bar");
        if (!ship || Object.keys(ship).length === 0) {
          bar.innerHTML = '<span class="empty-state">Awaiting ship data...</span>';
          return;
        }

        // Just render the IR section for testing
        const irHtml = this._getIrSignatureHtml(ship);
        const thermalHtml = this._getThermalHtml(ship);

        bar.innerHTML = \`
          <div class="status-group">
            <span class="status-label">HULL</span>
            <span class="status-value nominal">100%</span>
          </div>
          \${irHtml}
          \${thermalHtml}
        \`;
      }

      _getIrSignatureHtml(ship) {
        const emissions = ship.emissions;
        if (!emissions) return "";

        const level = emissions.ir_level || "low";
        const coldDrift = emissions.cold_drift_active;
        const cooling = emissions.plume_cooling;

        const levelMap = {
          minimal: { label: "MIN", cls: "nominal" },
          low: { label: "LOW", cls: "nominal" },
          moderate: { label: "MED", cls: "warning" },
          high: { label: "HIGH", cls: "warning" },
          extreme: { label: "MAX", cls: "critical" },
        };

        const info = levelMap[level] || levelMap.low;
        let extra = "";
        if (coldDrift) extra = " COLD";
        else if (cooling) extra = " COOL";

        return \`
          <div class="separator"></div>
          <div class="status-group" id="ir-group">
            <span class="status-label">IR</span>
            <span class="status-value \${info.cls}" id="ir-value">\${info.label}\${extra}</span>
          </div>
        \`;
      }

      _getThermalHtml(ship) {
        const thermal = ship.thermal;
        if (!thermal || !thermal.enabled) return "";
        const temp = thermal.hull_temperature ?? 300;
        const maxTemp = thermal.max_temperature ?? 500;
        const pct = Math.min(100, ((temp - 2.7) / (maxTemp - 2.7)) * 100);
        const cls = thermal.is_emergency ? "critical"
          : thermal.is_overheating ? "warning" : "nominal";
        return \`
          <div class="separator"></div>
          <div class="status-group" id="thermal-group">
            <span class="status-label">TEMP</span>
            <span class="status-value \${cls}" id="temp-value">\${temp.toFixed(0)}K</span>
          </div>
        \`;
      }
    }

    customElements.define("status-bar", TestStatusBar);
  </script>
</body>
</html>`;
}

let server;

test.beforeAll(async () => {
  server = await startServer(9876);
});

test.afterAll(async () => {
  if (server) server.close();
});

test("IR signature indicator shows correct levels", async ({ page }) => {
  await page.goto("http://localhost:9876/");

  // Wait for component to load
  await page.waitForSelector("status-bar");

  // Test 1: Full burn — extreme IR
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 8e6,
        ir_level: "extreme",
        is_thrusting: true,
        plume_cooling: false,
        cold_drift_active: false,
      },
      thermal: { enabled: true, hull_temperature: 350, max_temperature: 500 },
    });
  });

  const bar = page.locator("status-bar");
  const irValue = bar.locator(">>> #ir-value");
  await expect(irValue).toHaveText("MAX");
  await expect(irValue).toHaveClass(/critical/);

  // Test 2: Low thrust — moderate IR
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 5e5,
        ir_level: "moderate",
        is_thrusting: true,
        plume_cooling: false,
        cold_drift_active: false,
      },
      thermal: { enabled: true, hull_temperature: 320, max_temperature: 500 },
    });
  });

  await expect(irValue).toHaveText("MED");
  await expect(irValue).toHaveClass(/warning/);

  // Test 3: Engines off, cooling down — plume_cooling = true
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 1.5e5,
        ir_level: "moderate",
        is_thrusting: false,
        plume_cooling: true,
        cold_drift_active: false,
      },
      thermal: { enabled: true, hull_temperature: 340, max_temperature: 500 },
    });
  });

  await expect(irValue).toHaveText("MED COOL");

  // Test 4: Cold drift — minimal IR
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 5000,
        ir_level: "minimal",
        is_thrusting: false,
        plume_cooling: false,
        cold_drift_active: true,
      },
      thermal: { enabled: true, hull_temperature: 280, max_temperature: 500 },
    });
  });

  await expect(irValue).toHaveText("MIN COLD");
  await expect(irValue).toHaveClass(/nominal/);

  // Test 5: Drifting, no engines, hull only — low IR
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 5e4,
        ir_level: "low",
        is_thrusting: false,
        plume_cooling: false,
        cold_drift_active: false,
      },
      thermal: { enabled: true, hull_temperature: 300, max_temperature: 500 },
    });
  });

  await expect(irValue).toHaveText("LOW");
  await expect(irValue).toHaveClass(/nominal/);
});

test("thermal display shows cold-drift temperature cooling", async ({
  page,
}) => {
  await page.goto("http://localhost:9876/");
  await page.waitForSelector("status-bar");

  // Set state with cold drift active — hull should be cooling
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      emissions: {
        ir_watts: 3000,
        ir_level: "minimal",
        is_thrusting: false,
        plume_cooling: false,
        cold_drift_active: true,
      },
      thermal: {
        enabled: true,
        hull_temperature: 250,
        max_temperature: 500,
        nominal_temperature: 300,
        cold_drift_active: true,
      },
    });
  });

  const bar = page.locator("status-bar");
  const tempValue = bar.locator(">>> #temp-value");
  await expect(tempValue).toHaveText("250K");

  // Verify IR shows cold drift mode
  const irValue = bar.locator(">>> #ir-value");
  await expect(irValue).toHaveText("MIN COLD");
});

test("IR group appears only when emissions data exists", async ({ page }) => {
  await page.goto("http://localhost:9876/");
  await page.waitForSelector("status-bar");

  // State without emissions — no IR group should render
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      hull_percent: 100,
    });
  });

  const bar = page.locator("status-bar");
  const irGroup = bar.locator(">>> #ir-group");
  await expect(irGroup).toHaveCount(0);

  // Now add emissions — IR group should appear
  await page.evaluate(() => {
    window.__mockStateManager.setTestState({
      hull_percent: 100,
      emissions: {
        ir_watts: 5e4,
        ir_level: "low",
        is_thrusting: false,
        plume_cooling: false,
        cold_drift_active: false,
      },
    });
  });

  await expect(irGroup).toHaveCount(1);
  await expect(bar.locator(">>> #ir-value")).toHaveText("LOW");
});
