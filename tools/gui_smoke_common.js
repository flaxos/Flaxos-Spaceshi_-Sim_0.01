const DEFAULT_OPTIONS = {
  durationMs: 8000,
  sampleMs: 1000,
  initialWaitMs: 2500,
  evaluateTimeoutMs: 2000,
  readyTimeoutMs: 10000,
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function withTimeout(promise, timeoutMs, label) {
  let timeoutId = null;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`${label} timed out after ${timeoutMs}ms`));
    }, timeoutMs);
  });

  try {
    return await Promise.race([promise, timeoutPromise]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function collectDebugSnapshot(page, label, evaluateTimeoutMs) {
  return withTimeout(
    page.evaluate(() => window._flaxosDebugState()),
    evaluateTimeoutMs,
    label,
  );
}

function normalizeMessage(message) {
  return String(message || "").replace(/\s+/g, " ").trim();
}

function summarizeMessages(messages, maxItems = 5) {
  const counts = new Map();
  for (const message of messages) {
    const normalized = normalizeMessage(message);
    if (!normalized) continue;
    counts.set(normalized, (counts.get(normalized) || 0) + 1);
  }

  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxItems)
    .map(([message, count]) => ({
      count,
      message: message.length > 220 ? `${message.slice(0, 217)}...` : message,
    }));
}

async function collectStartupState(page, evaluateTimeoutMs) {
  return withTimeout(
    page.evaluate(() => {
      const scenarioLoader = document.querySelector("scenario-loader");
      const tierSelector = document.querySelector("tier-selector");
      const loaderRoot = scenarioLoader?.shadowRoot || null;

      const menuState = loaderRoot?.querySelector(".title-screen")
        ? "title"
        : loaderRoot?.querySelector(".mission-select")
          ? "mission_select"
          : loaderRoot?.querySelector(".quick-play")
            ? "quick_play"
            : loaderRoot?.querySelector(".lobby-view")
              ? "lobby"
              : loaderRoot?.querySelector(".post-mission")
                ? "post_mission"
                : "unknown";

      const hasNewGameButton = !!loaderRoot?.querySelector("#btn-new-game");
      const hasQuickPlayButton = !!loaderRoot?.querySelector("#btn-quick-play");
      const hasJoinGameButton = !!loaderRoot?.querySelector("#btn-join-game");

      return {
        hasScenarioLoader: !!scenarioLoader,
        hasTierSelector: !!tierSelector,
        hasCpuAssistButton: !!tierSelector?.shadowRoot?.querySelector('button[data-tier="cpu-assist"]'),
        hasNewGameButton,
        hasQuickPlayButton,
        hasJoinGameButton,
        menuState,
        primaryMenuReady: menuState === "title"
          ? hasNewGameButton && hasQuickPlayButton && hasJoinGameButton
          : menuState !== "unknown",
      };
    }),
    evaluateTimeoutMs,
    "startup controls snapshot",
  );
}

async function loadScenario(page, scenarioId, evaluateTimeoutMs) {
  return withTimeout(
    page.evaluate(async (id) => {
      const { wsClient } = window._flaxosModules || {};
      if (!wsClient) {
        throw new Error("wsClient unavailable");
      }
      const response = await wsClient.send("load_scenario", { scenario: id });
      const detail = {
        ...response,
        playerShipId: response?.playerShipId || response?.player_ship_id || null,
        shipsLoaded: response?.shipsLoaded || response?.ships_loaded || null,
        assignedShip: response?.assignedShip || response?.assigned_ship || response?.player_ship_id || null,
        autoAssigned: response?.autoAssigned ?? response?.auto_assigned ?? false,
      };
      document.dispatchEvent(new CustomEvent("scenario-loaded", {
        detail,
        bubbles: true,
        composed: true,
      }));
      return detail;
    }, scenarioId),
    Math.max(evaluateTimeoutMs, 15000),
    `load scenario ${scenarioId}`,
  );
}

async function switchView(page, view, evaluateTimeoutMs) {
  return withTimeout(
    page.locator("view-tabs").evaluate((host, targetView) => {
      const button = host.shadowRoot?.querySelector(`button[data-view="${targetView}"]`);
      if (!button) {
        throw new Error(`View button not found for ${targetView}`);
      }
      button.click();
      return {
        activeView: host.activeView,
        allowedViews: host.allowedViews,
      };
    }, view),
    evaluateTimeoutMs,
    `switch to view ${view}`,
  );
}

async function switchToCpuAssist(page, options) {
  const deadline = Date.now() + options.readyTimeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      return await withTimeout(
        page.locator("tier-selector").evaluate((host) => {
          const button = host.shadowRoot?.querySelector('button[data-tier="cpu-assist"]');
          if (!button) {
            throw new Error("CPU ASSIST button not found");
          }
          button.click();
          return {
            tier: window.controlTier,
            bodyClasses: Array.from(document.body.classList),
          };
        }),
        options.evaluateTimeoutMs,
        "cpu-assist click",
      );
    } catch (error) {
      lastError = error;
      await sleep(250);
    }
  }

  throw lastError || new Error("CPU ASSIST button not found");
}

async function waitForConnectedSnapshot(page, options) {
  const deadline = Date.now() + options.readyTimeoutMs;
  let lastSnapshot = null;
  let lastStartup = null;

  while (Date.now() < deadline) {
    try {
      lastStartup = await collectStartupState(page, options.evaluateTimeoutMs);
      lastSnapshot = await collectDebugSnapshot(
        page,
        "ready debug snapshot",
        options.evaluateTimeoutMs,
      );
      if (
        lastSnapshot?.wsStatus === "connected" &&
        lastStartup?.hasCpuAssistButton &&
        lastStartup?.hasScenarioLoader &&
        lastStartup?.primaryMenuReady
      ) {
        return lastSnapshot;
      }
    } catch {
      // App may still be booting; keep waiting within the deadline.
    }
    await sleep(500);
  }

  if (lastSnapshot) {
    throw new Error(
      `GUI did not become ready before timeout (ws=${lastSnapshot.wsStatus || "unknown"}, tier=${lastSnapshot.tier || "unknown"}, startup=${JSON.stringify(lastStartup)})`,
    );
  }

  return collectDebugSnapshot(page, "initial debug snapshot", options.evaluateTimeoutMs);
}

async function waitForScenarioSnapshot(page, options) {
  const deadline = Date.now() + options.readyTimeoutMs;
  let lastSnapshot = null;

  while (Date.now() < deadline) {
    lastSnapshot = await collectDebugSnapshot(
      page,
      "scenario assignment snapshot",
      options.evaluateTimeoutMs,
    );
    if (lastSnapshot?.playerShipId && lastSnapshot?.gameState === "playing") {
      return lastSnapshot;
    }
    await sleep(250);
  }

  return lastSnapshot;
}

function analyzeSmokeResult(result) {
  const issues = [];
  const startup = result.startup || {};
  const afterSwitch = result.afterSwitch || {};
  const samples = result.samples || [];
  const lastSample = samples[samples.length - 1] || afterSwitch;
  const baselineSnapshot = result.afterScenario || result.before || {};
  const beforeBlocked = baselineSnapshot.blockedCommandTotal || 0;
  const afterBlocked = lastSample?.blockedCommandTotal || 0;
  const consoleErrors = summarizeMessages(
    (result.consoleEntries || [])
      .filter((entry) => entry.type === "error")
      .map((entry) => entry.text),
  );
  const diagnosticErrors = summarizeMessages(
    [
      ...((afterSwitch?.recentErrors || []).map((entry) => entry.message)),
      ...((lastSample?.recentErrors || []).map((entry) => entry.message)),
    ],
  );

  if (result.crashes?.length) {
    issues.push(`page crashed ${result.crashes.length} time(s)`);
  }

  if (result.snapshotErrors?.length) {
    issues.push(`snapshot collection failed ${result.snapshotErrors.length} time(s)`);
  }

  if (!startup.hasScenarioLoader) {
    issues.push("scenario-loader did not render at startup");
  }

  if (!startup.hasCpuAssistButton) {
    issues.push("CPU ASSIST button was not present at startup");
  }

  if (!startup.primaryMenuReady) {
    issues.push(`startup controls were not ready (menu=${startup.menuState || "unknown"})`);
  }

  if ((afterSwitch.tier || null) !== "cpu-assist") {
    issues.push(`tier did not switch to cpu-assist (got ${afterSwitch.tier || "unknown"})`);
  }

  if ((afterSwitch.wsStatus || lastSample?.wsStatus || "disconnected") !== "connected") {
    issues.push(`websocket did not remain connected (got ${lastSample?.wsStatus || afterSwitch.wsStatus || "unknown"})`);
  }

  if (samples.length === 0) {
    issues.push("no post-switch debug samples were collected");
  }

  if (result.scenarioId && !result.afterScenario?.playerShipId) {
    issues.push(`scenario ${result.scenarioId} did not assign a player ship`);
  }

  if (result.scenarioId && result.afterScenario?.gameState !== "playing") {
    issues.push(`scenario ${result.scenarioId} did not transition the app to playing`);
  }

  if (result.targetView && (afterSwitch.activeView || null) !== result.targetView) {
    issues.push(`active view did not switch to ${result.targetView} (got ${afterSwitch.activeView || "unknown"})`);
  }

  if (afterBlocked > beforeBlocked) {
    issues.push(`blocked ship commands increased after CPU assist (${beforeBlocked} -> ${afterBlocked})`);
  }

  for (const pollerName of result.expectedPollers || []) {
    const initialPoller = afterSwitch?.diagnostics?.runtime?.pollers?.[pollerName];
    const finalPoller = lastSample?.diagnostics?.runtime?.pollers?.[pollerName];
    if (!finalPoller) {
      issues.push(`expected poller ${pollerName} was not registered`);
      continue;
    }
    if (!finalPoller.eligible) {
      issues.push(`expected poller ${pollerName} was not eligible (${finalPoller.skipReason || "inactive"})`);
      continue;
    }
    if ((finalPoller.runCount || 0) <= (initialPoller?.runCount || 0)) {
      issues.push(`expected poller ${pollerName} did not advance during smoke window`);
    }
  }

  if ((lastSample?.alarms || []).length > 0) {
    issues.push(`runtime alarms reported: ${JSON.stringify(lastSample.alarms)}`);
  }

  if ((result.pageErrors || []).length > 0) {
    issues.push(`page errors observed: ${result.pageErrors.length}`);
  }

  if (consoleErrors.length > 0) {
    issues.push(`console errors observed: ${JSON.stringify(consoleErrors)}`);
  }

  if (diagnosticErrors.length > 0) {
    issues.push(`diagnostic errors observed: ${JSON.stringify(diagnosticErrors)}`);
  }

  return issues;
}

async function runGuiCpuAssistSmoke({ page, url, ...overrides }) {
  const options = { ...DEFAULT_OPTIONS, ...overrides };
  const consoleEntries = [];
  const pageErrors = [];
  const crashes = [];
  const snapshotErrors = [];

  page.on("console", (msg) => {
    consoleEntries.push({
      type: msg.type(),
      text: msg.text(),
    });
  });
  page.on("pageerror", (error) => {
    pageErrors.push(String(error));
  });
  page.on("crash", () => {
    crashes.push("page crashed");
  });

  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(options.initialWaitMs);

  const before = await waitForConnectedSnapshot(page, options);
  const startup = await collectStartupState(page, options.evaluateTimeoutMs);
  let loadResult = null;
  let afterScenario = null;
  let viewResult = null;

  if (options.scenarioId) {
    loadResult = await loadScenario(page, options.scenarioId, options.evaluateTimeoutMs);
    afterScenario = await waitForScenarioSnapshot(page, options);
  }

  if (options.targetView) {
    viewResult = await switchView(page, options.targetView, options.evaluateTimeoutMs);
  }

  const clickResult = await switchToCpuAssist(page, options);
  const afterSwitch = await collectDebugSnapshot(page, "post-click debug snapshot", options.evaluateTimeoutMs);

  const samples = [];
  const sampleCount = Math.max(1, Math.floor(options.durationMs / options.sampleMs));
  for (let index = 0; index < sampleCount; index += 1) {
    await sleep(options.sampleMs);
    try {
      const snapshot = await collectDebugSnapshot(
        page,
        `debug sample ${index + 1}`,
        options.evaluateTimeoutMs,
      );
      samples.push(snapshot);
    } catch (error) {
      snapshotErrors.push(String(error));
      break;
    }
  }

  const result = {
    url,
    scenarioId: options.scenarioId || null,
    targetView: options.targetView || null,
    expectedPollers: options.expectedPollers || [],
    startup,
    clickResult,
    before,
    loadResult,
    afterScenario,
    viewResult,
    afterSwitch,
    samples,
    consoleEntries: consoleEntries.slice(-100),
    pageErrors,
    crashes,
    snapshotErrors,
  };
  result.issues = analyzeSmokeResult(result);
  return result;
}

module.exports = {
  runGuiCpuAssistSmoke,
  analyzeSmokeResult,
};
