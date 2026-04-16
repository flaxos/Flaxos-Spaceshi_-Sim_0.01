#!/usr/bin/env node

const http = require("http");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");
const { runGuiCpuAssistSmoke } = require("./gui_smoke_common");

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
    if (arg === "--scenario" && next) options.scenarioId = next;
    if (arg === "--view" && next) options.targetView = next;
    if (arg === "--expect-poller" && next) {
      options.expectedPollers.push(next);
    }
  }

  return options;
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

async function waitForHttp(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await httpReady(url)) return true;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function startGuiStack(python) {
  const child = spawn(
    python,
    ["tools/start_gui_stack.py", "--no-browser"],
    {
      cwd: REPO_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  const logLines = [];
  const pushChunk = (prefix, chunk) => {
    const lines = chunk.toString().split(/\r?\n/).filter(Boolean);
    for (const line of lines) {
      logLines.push(`${prefix}${line}`);
      if (logLines.length > 100) logLines.shift();
    }
  };

  child.stdout.on("data", (chunk) => pushChunk("", chunk));
  child.stderr.on("data", (chunk) => pushChunk("[stderr] ", chunk));

  return { child, logLines };
}

async function stopGuiStack(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (child.exitCode === null) child.kill("SIGKILL");
      resolve();
    }, 5000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
  child.stdout?.destroy();
  child.stderr?.destroy();
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  let stack = null;
  let browser = null;

  try {
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

    browser = await chromium.launch({ headless: true });
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
    if (browser) {
      await browser.close();
    }
    if (stack) {
      await stopGuiStack(stack.child);
    }
  }
}

main()
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
