const { test, expect } = require("@playwright/test");
const { runGuiCpuAssistSmoke } = require("./tools/gui_smoke_common");

test("real GUI stays responsive after switching to CPU ASSIST with no ship assigned", async ({ page }) => {
  test.setTimeout(45000);

  const result = await runGuiCpuAssistSmoke({
    page,
    url: process.env.GUI_BASE_URL || "http://127.0.0.1:3100/",
    durationMs: 8000,
    sampleMs: 1000,
    initialWaitMs: 2500,
    evaluateTimeoutMs: 2000,
  });

  expect(result.afterSwitch.tier).toBe("cpu-assist");
  expect(result.samples.length).toBeGreaterThanOrEqual(3);
  expect(result.issues, JSON.stringify(result, null, 2)).toEqual([]);
});

test("fleet CPU ASSIST stays responsive and advances pollers after scenario assignment", async ({ page }) => {
  test.setTimeout(45000);

  const result = await runGuiCpuAssistSmoke({
    page,
    url: process.env.GUI_BASE_URL || "http://127.0.0.1:3100/",
    durationMs: 8000,
    sampleMs: 1000,
    initialWaitMs: 2500,
    evaluateTimeoutMs: 2000,
    scenarioId: "01_tutorial_intercept",
    targetView: "fleet",
    expectedPollers: ["fleet-orders:auto-fleet-status"],
  });

  expect(result.afterScenario.playerShipId).toBeTruthy();
  expect(result.afterSwitch.tier).toBe("cpu-assist");
  expect(result.afterSwitch.activeView).toBe("fleet");
  expect(result.samples.length).toBeGreaterThanOrEqual(3);
  expect(result.issues, JSON.stringify(result, null, 2)).toEqual([]);
});
