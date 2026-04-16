const MAX_RECENT_LOGS = 50;
const MAX_RECENT_BLOCKS = 100;

function formatValue(value) {
  if (value instanceof Error) return `${value.name}: ${value.message}`;
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function nowIso() {
  return new Date().toISOString();
}

class RuntimeDiagnostics {
  constructor() {
    this._pollers = new Map();
    this._blockedCommands = new Map();
    this._recentBlocked = [];
    this._recentLogs = [];
    this._consoleInstalled = false;
    this._originalConsole = null;
  }

  installConsoleCapture() {
    if (this._consoleInstalled || typeof console === "undefined") return;

    this._originalConsole = {
      warn: console.warn.bind(console),
      error: console.error.bind(console),
    };

    ["warn", "error"].forEach((level) => {
      const original = this._originalConsole[level];
      console[level] = (...args) => {
        this.recordConsole(level, args);
        original(...args);
      };
    });

    this._consoleInstalled = true;
  }

  recordConsole(level, args) {
    const entry = {
      level,
      message: args.map(formatValue).join(" "),
      ts: Date.now(),
      iso: nowIso(),
    };
    this._recentLogs.push(entry);
    while (this._recentLogs.length > MAX_RECENT_LOGS) {
      this._recentLogs.shift();
    }
  }

  registerPoller(name, meta = {}) {
    const existing = this._pollers.get(name) || {
      name,
      createdAt: Date.now(),
      createdAtIso: nowIso(),
      runCount: 0,
      errorCount: 0,
      state: "registered",
      eligible: false,
    };
    const next = { ...existing, ...meta, name };
    this._pollers.set(name, next);
    return next;
  }

  getPoller(name) {
    return this._pollers.get(name) || null;
  }

  updatePoller(name, patch = {}) {
    const current = this.registerPoller(name);
    const next = { ...current, ...patch, name };
    this._pollers.set(name, next);
    return next;
  }

  unregisterPoller(name) {
    this._pollers.delete(name);
  }

  recordBlockedCommand(command, reason = "unknown") {
    const prev = this._blockedCommands.get(command) || {
      command,
      count: 0,
      lastReason: reason,
      firstBlockedAt: Date.now(),
      firstBlockedAtIso: nowIso(),
    };
    const next = {
      ...prev,
      count: prev.count + 1,
      lastReason: reason,
      lastBlockedAt: Date.now(),
      lastBlockedAtIso: nowIso(),
    };
    this._blockedCommands.set(command, next);

    this._recentBlocked.push({
      command,
      reason,
      ts: next.lastBlockedAt,
      iso: next.lastBlockedAtIso,
    });
    while (this._recentBlocked.length > MAX_RECENT_BLOCKS) {
      this._recentBlocked.shift();
    }
  }

  _getRecentLogs(level) {
    return this._recentLogs.filter((entry) => entry.level === level).slice(-10);
  }

  _computeAlarms() {
    const alarms = [];

    for (const block of this._blockedCommands.values()) {
      if (block.count >= 5) {
        alarms.push({
          type: "blocked_command_flood",
          command: block.command,
          count: block.count,
          reason: block.lastReason,
        });
      }
    }

    for (const poller of this._pollers.values()) {
      if (poller.errorCount >= 3) {
        alarms.push({
          type: "poller_error",
          poller: poller.name,
          count: poller.errorCount,
          lastError: poller.lastError || null,
        });
      }
    }

    return alarms;
  }

  getSnapshot() {
    const pollers = {};
    for (const [name, poller] of this._pollers.entries()) {
      pollers[name] = {
        name,
        owner: poller.owner || null,
        state: poller.state,
        eligible: !!poller.eligible,
        intervalMs: poller.intervalMs || null,
        idleIntervalMs: poller.idleIntervalMs || null,
        runCount: poller.runCount || 0,
        errorCount: poller.errorCount || 0,
        lastRunAt: poller.lastRunAt || null,
        lastSuccessAt: poller.lastSuccessAt || null,
        lastErrorAt: poller.lastErrorAt || null,
        nextRunAt: poller.nextRunAt || null,
        skipReason: poller.skipReason || null,
        lastError: poller.lastError || null,
        view: poller.view || null,
        tier: poller.tier || null,
      };
    }

    const activePollers = Object.values(pollers)
      .filter((poller) => poller.eligible && poller.state !== "stopped")
      .map((poller) => ({
        name: poller.name,
        state: poller.state,
        intervalMs: poller.intervalMs,
        nextRunAt: poller.nextRunAt,
      }));

    const blockedCommands = {};
    let blockedCommandTotal = 0;
    for (const [command, info] of this._blockedCommands.entries()) {
      blockedCommands[command] = info.count;
      blockedCommandTotal += info.count;
    }

    return {
      activePollers,
      pollers,
      blockedCommands,
      blockedCommandTotal,
      recentBlockedCommands: this._recentBlocked.slice(-10),
      recentWarnings: this._getRecentLogs("warn"),
      recentErrors: this._getRecentLogs("error"),
      alarms: this._computeAlarms(),
    };
  }
}

const runtimeDiagnostics = new RuntimeDiagnostics();

function isElementVisible(element) {
  if (!element?.isConnected) return false;

  const view = element.closest?.(".view-container");
  if (view && !view.classList.contains("active")) {
    return false;
  }

  const style = window.getComputedStyle?.(element);
  if (!style || style.display === "none" || style.visibility === "hidden") {
    return false;
  }

  return element.getClientRects().length > 0;
}

function getElementView(element) {
  const view = element?.closest?.(".view-container");
  if (!view?.id) return null;
  return view.id.replace(/^view-/, "");
}

function getPlayerShipId() {
  const modules = window._flaxosModules || window.flaxosApp || {};
  const stateManager = modules.stateManager;
  if (!stateManager) return null;

  const explicit = stateManager.getPlayerShipId?.();
  if (explicit) return explicit;

  const ship = stateManager.getShipState?.();
  return ship?.id || ship?.ship_id || null;
}

function normalizeGuardResult(result) {
  if (typeof result === "boolean") {
    return { ok: result, reason: result ? null : "inactive" };
  }
  if (!result || typeof result !== "object") {
    return { ok: !!result, reason: result ? null : "inactive" };
  }
  if ("ok" in result) return result;
  if ("eligible" in result) return { ...result, ok: !!result.eligible };
  return { ok: true, ...result };
}

export function evaluatePollerGuard(element, options = {}) {
  const modules = window._flaxosModules || window.flaxosApp || {};
  const wsClient = modules.wsClient;
  const tier = window.controlTier || "arcade";
  const view = getElementView(element);
  const shipId = getPlayerShipId();

  if (!element?.isConnected) {
    return { ok: false, reason: "dom_disconnected", tier, view, shipId };
  }

  if (options.requireVisible !== false && !isElementVisible(element)) {
    return { ok: false, reason: "hidden", tier, view, shipId };
  }

  if (options.tierAllowlist && !options.tierAllowlist.includes(tier)) {
    return { ok: false, reason: `tier:${tier}`, tier, view, shipId };
  }

  if (options.requireWs !== false && wsClient && !wsClient.isConnected) {
    return {
      ok: false,
      reason: `ws:${wsClient.status || "disconnected"}`,
      tier,
      view,
      shipId,
      wsStatus: wsClient.status || "disconnected",
    };
  }

  if (options.requireShip && !shipId) {
    return { ok: false, reason: "no_ship_id", tier, view, shipId: null };
  }

  if (typeof options.extraCheck === "function") {
    return normalizeGuardResult(options.extraCheck({
      tier,
      view,
      shipId,
      wsClient,
      element,
    }));
  }

  return {
    ok: true,
    tier,
    view,
    shipId,
    wsStatus: wsClient?.status || "unknown",
  };
}

export function createManagedPoller(name, config) {
  let timer = null;
  let started = false;
  let running = false;

  const intervalMs = config.intervalMs;
  const idleIntervalMs = config.idleIntervalMs || intervalMs;

  const updatePollerState = (patch = {}) => {
    const current = runtimeDiagnostics.getPoller(name);
    const base = current || {
      name,
      owner: config.owner || null,
      intervalMs,
      idleIntervalMs,
      runCount: 0,
      errorCount: 0,
    };
    runtimeDiagnostics.updatePoller(name, { ...base, ...patch });
  };

  const getGuard = () => {
    try {
      const guard = config.shouldRun ? config.shouldRun() : { ok: true };
      return normalizeGuardResult(guard);
    } catch (error) {
      return {
        ok: false,
        reason: `guard_error:${error.message}`,
        error,
      };
    }
  };

  const schedule = (delayMs) => {
    clearTimeout(timer);
    if (!started) return;
    const guard = getGuard();
    updatePollerState({
      state: guard.ok ? "scheduled" : "skipped",
      eligible: !!guard.ok,
      skipReason: guard.ok ? null : guard.reason || "inactive",
      nextRunAt: Date.now() + delayMs,
      tier: guard.tier || null,
      view: guard.view || null,
    });
    timer = window.setTimeout(() => {
      void tick("timer");
    }, delayMs);
  };

  const tick = async (trigger = "manual") => {
    if (!started) return;
    if (running) {
      schedule(idleIntervalMs);
      return;
    }

    const guard = getGuard();
    if (!guard.ok) {
      updatePollerState({
        state: "skipped",
        eligible: false,
        skipReason: guard.reason || "inactive",
        tier: guard.tier || null,
        view: guard.view || null,
      });
      schedule(idleIntervalMs);
      return;
    }

    running = true;
    updatePollerState({
      state: "running",
      eligible: true,
      skipReason: null,
      lastRunAt: Date.now(),
      tier: guard.tier || null,
      view: guard.view || null,
      shipId: guard.shipId || null,
      nextRunAt: null,
      lastTrigger: trigger,
    });

    try {
      const result = await config.run();
      const current = runtimeDiagnostics.getPoller(name);
      updatePollerState({
        state: "idle",
        eligible: true,
        lastSuccessAt: Date.now(),
        runCount: (current?.runCount || 0) + 1,
        lastResult: result === undefined ? null : formatValue(result),
      });
    } catch (error) {
      const current = runtimeDiagnostics.getPoller(name);
      updatePollerState({
        state: "error",
        eligible: true,
        lastErrorAt: Date.now(),
        lastError: error?.message || String(error),
        errorCount: (current?.errorCount || 0) + 1,
      });
      if (typeof config.onError === "function") {
        config.onError(error);
      }
    } finally {
      running = false;
      schedule(intervalMs);
    }
  };

  return {
    start({ immediate = true } = {}) {
      if (started) return;
      started = true;
      runtimeDiagnostics.registerPoller(name, {
        owner: config.owner || null,
        intervalMs,
        idleIntervalMs,
        state: "registered",
        eligible: false,
      });
      if (immediate) {
        void tick("start");
      } else {
        schedule(intervalMs);
      }
    },
    stop() {
      started = false;
      running = false;
      clearTimeout(timer);
      runtimeDiagnostics.unregisterPoller(name);
    },
    trigger(reason = "manual") {
      if (!started) return;
      clearTimeout(timer);
      void tick(reason);
    },
    sync() {
      if (!started) return;
      const guard = getGuard();
      updatePollerState({
        eligible: !!guard.ok,
        state: guard.ok ? "idle" : "skipped",
        skipReason: guard.ok ? null : guard.reason || "inactive",
        tier: guard.tier || null,
        view: guard.view || null,
      });
    },
  };
}

if (typeof window !== "undefined") {
  window._flaxosRuntimeDiagnostics = runtimeDiagnostics;
}

export { runtimeDiagnostics };
