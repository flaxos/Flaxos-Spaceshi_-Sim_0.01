const { test, expect } = require("@playwright/test");

async function waitForStartupControls(page, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastState = null;

  while (Date.now() < deadline) {
    lastState = await page.evaluate(() => {
      const loader = document.querySelector("scenario-loader");
      const root = loader?.shadowRoot || null;
      return {
        hasScenarioLoader: !!loader,
        hasNewGame: !!root?.querySelector("#btn-new-game"),
        hasQuickPlay: !!root?.querySelector("#btn-quick-play"),
        hasJoinGame: !!root?.querySelector("#btn-join-game"),
        debug: window._flaxosDebugState?.() || null,
      };
    });

    if (
      lastState.hasScenarioLoader &&
      lastState.hasNewGame &&
      lastState.hasQuickPlay &&
      lastState.hasJoinGame &&
      lastState.debug?.wsStatus === "connected"
    ) {
      return lastState;
    }

    await page.waitForTimeout(250);
  }

  throw new Error(`Startup controls did not become ready: ${JSON.stringify(lastState)}`);
}

async function waitForMissionSelect(page, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastState = null;

  while (Date.now() < deadline) {
    lastState = await page.evaluate(() => {
      const loader = document.querySelector("scenario-loader");
      const root = loader?.shadowRoot || null;
      return {
        hasMissionSelect: !!root?.querySelector(".mission-select"),
        hasMissionGrid: !!root?.querySelector(".mission-grid"),
        hasEmptyState: !!root?.querySelector(".empty-state"),
      };
    });

    if (lastState.hasMissionSelect && (lastState.hasMissionGrid || lastState.hasEmptyState)) {
      return lastState;
    }

    await page.waitForTimeout(250);
  }

  throw new Error(`Mission select did not open after clicking NEW GAME: ${JSON.stringify(lastState)}`);
}

test("startup controls render and NEW GAME works across reloads", async ({ page }) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 1280, height: 720 });

  const url = process.env.GUI_BASE_URL || "http://127.0.0.1:3100/";

  for (let iteration = 0; iteration < 3; iteration += 1) {
    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForTimeout(2000);

    const startup = await waitForStartupControls(page);
    expect(startup.hasScenarioLoader).toBe(true);
    expect(startup.hasNewGame).toBe(true);
    expect(startup.hasQuickPlay).toBe(true);
    expect(startup.hasJoinGame).toBe(true);
    expect(startup.debug?.wsStatus).toBe("connected");

    await page.locator("scenario-loader").evaluate((host) => {
      host.shadowRoot.querySelector("#btn-new-game")?.click();
    });

    const missionSelect = await waitForMissionSelect(page);
    expect(missionSelect.hasMissionSelect).toBe(true);
  }
});
