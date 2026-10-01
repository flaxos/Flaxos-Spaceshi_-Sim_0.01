#!/usr/bin/env node

const http = require("http");
const path = require("path");
const net = require("net");
const fs = require("fs/promises");
const { spawn } = require("child_process");
const { runGuiCpuAssistSmoke } = require("./gui_smoke_common");
const { runCrewSmoke } = require("./gui_crew_smoke");

const DEFAULT_URL = "http://127.0.0.1:3100/";
const DEFAULT_PYTHON = process.env.PYTHON || "python3";
const REPO_ROOT = path.resolve(__dirname, "..");

function parseArgs(argv) {
  const options = {
    url: DEFAULT_URL,
    durationMs: 8000,
    sampleMs: 1000,
    initialWaitMs: 2500,
    evaluateTimeoutMs: 2000,
    readyTimeoutMs: 10000,
    autoStart: argv.includes("--start-stack"),
    python: DEFAULT_PYTHON,
    scenarioId: null,
    targetView: null,
    expectedPollers: [],
    crew: argv.includes("--crew"),
    evidenceDir: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--url" && next) options.url = next;
    if (arg === "--duration-ms" && next) options.durationMs = Number(next);
    if (arg === "--sample-ms" && next) options.sampleMs = Number(next);
    if (arg === "--initial-wait-ms" && next) options.initialWaitMs = Number(next);
    if (arg === "--evaluate-timeout-ms" && next) options.evaluateTimeoutMs = Number(next);
    if (arg === "--ready-timeout-ms" && next) options.readyTimeoutMs = Number(next);
    if (arg === "--python" && next) options.python = next;
    if (arg === "--evidence-dir" && next) options.evidenceDir = path.resolve(next);
    if (arg === "--scenario" && next) options.scenarioId = next;
    if (arg === "--view" && next) options.targetView = next;
    if (arg === "--expect-poller" && next) {
      options.expectedPollers.push(next);
    }
  }

  return options;
}

async function assertPortsFree(ports = [8765, 8081, 3100]) {
  for (const port of ports) {
    await new Promise((resolve, reject) => {
      const probe = net.createServer();
      probe.once("error", () => reject(new Error(`Port ${port} is occupied; crew smoke will not attach to or stop an existing stack.`)));
      probe.listen({ port, host: "127.0.0.1", exclusive: true }, () => probe.close(resolve));
    });
  }
}

function redactStackLine(line) {
  return /password|game.code|secret|token/i.test(line) ? "[startup credential line omitted]" : line;
}

async function prepareEvidenceDirectory(directory) {
  if (!directory) return;
  await fs.mkdir(path.dirname(directory), { recursive: true });
  try { await fs.mkdir(directory, { mode: 0o700 }); }
  catch (error) {
    if (error.code === "EEXIST") throw new Error("Evidence directory already exists; choose a fresh path to keep runs separate.");
    throw error;
  }
}

function httpReady(url) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      resolve(response.statusCode >= 200 && response.statusCode < 500);
    });
    request.on("error", () => resolve(false));
    request.setTimeout(1000, () => {
      request.destroy();
      resolve(false);
    });
  });
}

async function waitForHttp(url, timeoutMs = 30000, shouldStop = () => false) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (shouldStop()) return false;
    if (await httpReady(url)) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function startGuiStack(python, ownedGroup = false) {
  const child = spawn(
    python,
    ["-u", "tools/start_gui_stack.py", "--no-browser"],
    {
      cwd: REPO_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      detached: ownedGroup,
    },
  );

  const logLines = [];
  const pushChunk = (prefix, chunk) => {
    const lines = chunk.toString().split(/\r?\n/).filter(Boolean);
    for (const line of lines) {
      logLines.push(`${prefix}${redactStackLine(line)}`);
      if (logLines.length > 100) logLines.shift();
    }
  };

  child.stdout.on("data", (chunk) => pushChunk("", chunk));
  child.stderr.on("data", (chunk) => pushChunk("[stderr] ", chunk));
  child.on("error", error => { child.spawnError = error; });
  child.ownedGroup = ownedGroup;
  child.ownedPorts = ownedGroup ? [8765, 8081, 3100] : [];

  return { child, logLines };
}

async function stopGuiStack(child) {
  if (!child) return;
  if (child.stopPromise) return child.stopPromise;
  child.stopPromise = (async () => {
    try {
      if (!child.pid) return;
      const signal = name => {
        try {
          if (child.ownedGroup) process.kill(-child.pid, name);
          else if (child.exitCode === null) child.kill(name);
        } catch (error) { if (error.code !== "ESRCH") throw error; }
      };
      signal("SIGTERM");
      if (child.exitCode === null && child.signalCode === null) {
        await new Promise((resolve) => {
          const timer = setTimeout(() => { signal("SIGKILL"); resolve(); }, 10000);
          child.once("exit", () => { clearTimeout(timer); resolve(); });
        });
      }
      // A launcher can exit before a stuck descendant. This process group was
      // created only by this smoke invocation; never signal a reused stack.
      if (child.ownedGroup) signal("SIGKILL");
      const deadline = Date.now() + 1500;
      while (child.ownedPorts?.length) {
        try { await assertPortsFree(child.ownedPorts); break; }
        catch (error) {
          if (Date.now() >= deadline) throw error;
          await new Promise(resolve => setTimeout(resolve, 25));
        }
      }
    } finally { child.stdout?.destroy(); child.stderr?.destroy(); }
  })();
  return child.stopPromise;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  let stack = null;
  let browser = null;
  let interrupted = null;
  const onSignal = signal => {
    interrupted = signal;
    void browser?.close().catch(() => {});
    if (stack) void stopGuiStack(stack.child).catch(() => {});
  };
  const onInt = () => onSignal("SIGINT"), onTerm = () => onSignal("SIGTERM");
  process.once("SIGINT", onInt);
  process.once("SIGTERM", onTerm);

  try {
    if (options.crew) {
      if (!options.autoStart || options.url !== DEFAULT_URL || options.scenarioId || options.targetView || options.expectedPollers.length) {
        throw new Error("Crew smoke requires --crew --start-stack on the default loopback ports and fixed 07_docking_test scenario; use a fresh checkout.");
      }
      if (process.platform === "win32") throw new Error("Owned crew smoke currently requires a POSIX process group (Linux/macOS).");
      await assertPortsFree();
      await prepareEvidenceDirectory(options.evidenceDir);
      stack = startGuiStack(options.python, true);
      const stopped = () => !!(interrupted || stack.child.spawnError || stack.child.exitCode !== null || stack.child.signalCode !== null);
      if (!(await waitForHttp(options.url, 30000, stopped))) {
        throw new Error("Owned GUI stack failed to start.");
      }
      // The launcher checks every child at one-second intervals. Let it detect
      // a failed TCP/WS bind before any scenario/ownership mutation can run.
      await new Promise(resolve => setTimeout(resolve, 1500));
      if (stopped()) throw new Error("Owned GUI stack did not remain healthy after startup.");
    }
    let startedStack = false;
    if (!(await httpReady(options.url))) {
      if (!options.autoStart) {
        throw new Error(`GUI is not reachable at ${options.url}. Re-run with --start-stack or start the GUI stack manually.`);
      }
      stack = startGuiStack(options.python);
      startedStack = true;
      const ready = await waitForHttp(options.url, 30000);
      if (!ready) {
        throw new Error(`Timed out waiting for GUI HTTP server at ${options.url}`);
      }
    }

    const { chromium } = require("playwright");
    browser = await chromium.launch({ headless: true, ...(process.env.FLAXOS_CHROMIUM ? { executablePath: process.env.FLAXOS_CHROMIUM } : {}) });
    if (options.crew) {
      const result = await runCrewSmoke({ browser, url: options.url, evidenceDir: options.evidenceDir, repoRoot: REPO_ROOT });
      await browser.close(); browser = null;
      await stopGuiStack(stack.child); stack = null;
      await assertPortsFree();
      result.ownedStackStopped = true;
      if (options.evidenceDir) await fs.writeFile(path.join(options.evidenceDir, "crew-smoke-result.json"), JSON.stringify(result, null, 2), { mode: 0o600 });
      console.log(JSON.stringify({ ...result, snapshots: result.snapshots.map(row => ({ phase: row.phase })) }, null, 2));
      return;
    }
    const page = await browser.newPage();
    const result = await runGuiCpuAssistSmoke({
      page,
      url: options.url,
      durationMs: options.durationMs,
      sampleMs: options.sampleMs,
      initialWaitMs: options.initialWaitMs,
      evaluateTimeoutMs: options.evaluateTimeoutMs,
      readyTimeoutMs: options.readyTimeoutMs,
      scenarioId: options.scenarioId,
      targetView: options.targetView,
      expectedPollers: options.expectedPollers,
    });
    result.startedStack = startedStack;
    if (stack) {
      result.stackLogs = stack.logLines.slice(-40);
    }

    console.log(JSON.stringify(result, null, 2));
    if (result.issues.length > 0) {
      process.exitCode = 1;
    }
  } finally {
    try { if (browser) await browser.close(); }
    finally {
      try { if (stack) await stopGuiStack(stack.child); }
      finally {
        process.removeListener("SIGINT", onInt);
        process.removeListener("SIGTERM", onTerm);
      }
    }
  }
}

if (require.main === module) main()
  .then(() => {
    process.exit(process.exitCode || 0);
  })
  .catch((error) => {
    console.error(JSON.stringify({
      ok: false,
      error: error.message,
    }, null, 2));
    process.exit(1);
  });

module.exports = { parseArgs, assertPortsFree, redactStackLine, prepareEvidenceDirectory, stopGuiStack };
