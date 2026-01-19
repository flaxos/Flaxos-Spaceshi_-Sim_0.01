const logPanel = document.getElementById("log");
let latestUpdateInfo = null;

function appendLog(message, type = "info") {
  const item = document.createElement("div");
  item.className = `log-item ${type}`;
  item.textContent = message;
  logPanel.prepend(item);
}

// Update-related functions
async function loadVersionInfo() {
  try {
    const response = await fetch("/api/version");
    const data = await response.json();

    document.getElementById("current-version").textContent = `v${data.version}`;
    document.getElementById("current-build").textContent = data.build;
    document.getElementById("release-date").textContent = data.release_date;

    return data;
  } catch (error) {
    appendLog(`Failed to load version info: ${error}`, "error");
  }
}

async function checkForUpdates() {
  const statusDiv = document.getElementById("update-status");
  const applyBtn = document.getElementById("apply-update-btn");
  const changelogDiv = document.getElementById("update-changelog");

  statusDiv.textContent = "Checking for updates...";
  statusDiv.className = "update-status info";

  try {
    const response = await fetch("/api/check_update");
    const data = await response.json();

    if (data.available) {
      latestUpdateInfo = data.update_info;
      statusDiv.textContent = `Update available: v${data.update_info.version}`;
      statusDiv.className = "update-status success";
      applyBtn.style.display = "inline-block";

      // Show changelog
      changelogDiv.innerHTML = `<h3>What's New:</h3><pre>${data.update_info.body || 'No changelog available'}</pre>`;
      changelogDiv.style.display = "block";

      appendLog(`Update available: v${data.update_info.version}`, "info");
    } else {
      statusDiv.textContent = `No updates available (current: v${data.current_version})`;
      statusDiv.className = "update-status success";
      applyBtn.style.display = "none";
      changelogDiv.style.display = "none";

      appendLog("System is up to date", "info");
    }
  } catch (error) {
    statusDiv.textContent = `Update check failed: ${error}`;
    statusDiv.className = "update-status error";
    applyBtn.style.display = "none";
    changelogDiv.style.display = "none";

    appendLog(`Update check failed: ${error}`, "error");
  }
}

async function applyUpdate() {
  const statusDiv = document.getElementById("update-status");
  const applyBtn = document.getElementById("apply-update-btn");

  if (!confirm("Apply update? The application will need to be restarted.")) {
    return;
  }

  statusDiv.textContent = "Downloading and applying update... This may take a few minutes.";
  statusDiv.className = "update-status info";
  applyBtn.disabled = true;

  appendLog("Starting update process...", "info");

  try {
    const response = await fetch("/api/apply_update", { method: "POST" });
    const data = await response.json();

    if (data.success) {
      statusDiv.textContent = data.message;
      statusDiv.className = "update-status success";

      appendLog(data.message, "info");
      appendLog("Please restart the application!", "info");

      // Reload version info
      setTimeout(loadVersionInfo, 2000);
    } else {
      statusDiv.textContent = data.message;
      statusDiv.className = "update-status error";
      applyBtn.disabled = false;

      appendLog(`Update failed: ${data.message}`, "error");
    }
  } catch (error) {
    statusDiv.textContent = `Update failed: ${error}`;
    statusDiv.className = "update-status error";
    applyBtn.disabled = false;

    appendLog(`Update failed: ${error}`, "error");
  }
}

function getConnection() {
  return {
    host: document.getElementById("host").value.trim(),
    port: Number(document.getElementById("port").value),
    ship: document.getElementById("ship").value.trim(),
  };
}

async function sendCommand(command, extra = {}) {
  const { host, port, ship } = getConnection();
  const payload = { cmd: command, ship, ...extra };

  appendLog(`>> ${JSON.stringify(payload)}`, "request");

  try {
    const response = await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, port, payload }),
    });

    const data = await response.json();
    if (!data.ok) {
      appendLog(`!! ${data.error}`, "error");
      return;
    }

    appendLog(`<< ${JSON.stringify(data.response)}`, "response");
  } catch (error) {
    appendLog(`!! ${error}`, "error");
  }
}

function setUpActions() {
  document.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;

      if (action === "test-connection") {
        return sendCommand("get_state", {});
      }

      if (action === "get-state") {
        return sendCommand("get_state", {});
      }

      if (action === "set-thrust") {
        return sendCommand("set_thrust", {
          x: Number(document.getElementById("thrust-x").value),
          y: Number(document.getElementById("thrust-y").value),
          z: Number(document.getElementById("thrust-z").value),
        });
      }

      if (action === "set-course") {
        return sendCommand("set_course", {
          x: Number(document.getElementById("course-x").value),
          y: Number(document.getElementById("course-y").value),
          z: Number(document.getElementById("course-z").value),
        });
      }

      if (action === "set-autopilot") {
        return sendCommand("autopilot", {
          enabled: document.getElementById("autopilot").value === "true",
        });
      }

      if (action === "set-target") {
        return sendCommand("set_target", {
          target: document.getElementById("nav-target").value.trim(),
        });
      }

      if (action === "ping-sensors") {
        return sendCommand("ping_sensors", {
          mode: document.getElementById("sensor-mode").value,
          count: Number(document.getElementById("sensor-count").value),
        });
      }

      if (action === "fire-weapon") {
        return sendCommand("fire_weapon", {
          target: document.getElementById("tactical-target").value.trim(),
        });
      }

      if (action === "toggle-system") {
        return sendCommand("toggle_system", {
          system: document.getElementById("power-system").value.trim(),
          state: document.getElementById("power-state").checked ? 1 : 0,
        });
      }

      if (action === "set-power-allocation") {
        return sendCommand("set_power_allocation", {
          primary: Number(document.getElementById("power-primary").value),
          secondary: Number(document.getElementById("power-secondary").value),
          tertiary: Number(document.getElementById("power-tertiary").value),
        });
      }

      if (action === "check-update") {
        return checkForUpdates();
      }

      if (action === "apply-update") {
        return applyUpdate();
      }

      appendLog(`Unknown action: ${action}`, "error");
    });
  });
}

// Initialize
setUpActions();
loadVersionInfo();

// Auto-check for updates on page load (optional, after 5 seconds)
setTimeout(() => {
  checkForUpdates();
}, 5000);
