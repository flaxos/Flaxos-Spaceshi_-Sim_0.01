const { test, expect } = require("@playwright/test");

async function waitForDebugState(page, predicate, label, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastSnapshot = null;

  while (Date.now() < deadline) {
    lastSnapshot = await page.evaluate(() => window._flaxosDebugState?.());
    if (lastSnapshot && predicate(lastSnapshot)) {
      return lastSnapshot;
    }
    await page.waitForTimeout(250);
  }

  throw new Error(`Timed out waiting for ${label}: ${JSON.stringify(lastSnapshot)}`);
}

test("mission list selection keeps scroll position", async ({ page }) => {
  test.setTimeout(30000);
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.goto(process.env.GUI_BASE_URL || "http://127.0.0.1:3100/", {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await page.waitForTimeout(2500);

  await page.locator("scenario-loader").evaluate((host) => {
    host.shadowRoot.querySelector("#btn-new-game")?.click();
  });

  const result = await page.locator("scenario-loader").evaluate(async (host) => {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    for (let i = 0; i < 40; i += 1) {
      const grid = host.shadowRoot.querySelector(".mission-grid");
      if (
        grid &&
        grid.querySelectorAll(".mission-card").length > 10 &&
        grid.scrollHeight > grid.clientHeight + 20
      ) {
        break;
      }
      await sleep(250);
    }

    const grid = host.shadowRoot.querySelector(".mission-grid");
    const cards = Array.from(host.shadowRoot.querySelectorAll(".mission-card"));
    if (!grid || cards.length < 2) {
      throw new Error("Mission list did not load");
    }
    if (grid.scrollHeight <= grid.clientHeight + 20) {
      throw new Error(`Mission list was not scrollable: scrollHeight=${grid.scrollHeight}, clientHeight=${grid.clientHeight}, cards=${cards.length}`);
    }

    grid.scrollTop = grid.scrollHeight;
    await sleep(50);

    const target = cards[cards.length - 1];
    const targetName = target.querySelector(".card-name")?.textContent?.trim() || null;
    const before = grid.scrollTop;
    target.click();
    await sleep(100);

    const newGrid = host.shadowRoot.querySelector(".mission-grid");
    const selected = host.shadowRoot.querySelector(".mission-card.selected .card-name")?.textContent?.trim() || null;

    return {
      beforeScrollTop: before,
      afterScrollTop: newGrid?.scrollTop ?? null,
      targetName,
      selected,
    };
  });

  expect(result.targetName).toBeTruthy();
  expect(result.selected).toBe(result.targetName);
  expect(result.beforeScrollTop).toBeGreaterThan(0);
  expect(result.afterScrollTop).toBeGreaterThan(Math.max(0, result.beforeScrollTop - 40));
});

test("launching a mission from the list enters playing without a tier toggle workaround", async ({ page }) => {
  test.setTimeout(40000);
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.goto(process.env.GUI_BASE_URL || "http://127.0.0.1:3100/", {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await page.waitForTimeout(2500);

  await waitForDebugState(page, (snapshot) => snapshot.wsStatus === "connected", "ws connection");

  await page.locator("scenario-loader").evaluate((host) => {
    host.shadowRoot.querySelector("#btn-new-game")?.click();
  });

  await page.locator("scenario-loader").evaluate(async (host) => {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    for (let i = 0; i < 40; i += 1) {
      const launchButton = host.shadowRoot.querySelector(".mission-card .btn-launch");
      if (launchButton) {
        launchButton.click();
        return;
      }
      await sleep(250);
    }
    throw new Error("Mission launch button not found");
  });

  const snapshot = await waitForDebugState(
    page,
    (state) => state.gameState === "playing" && !!state.playerShipId,
    "mission launch state",
    20000,
  );

  expect(snapshot.gameState).toBe("playing");
  expect(snapshot.playerShipId).toBeTruthy();
});
