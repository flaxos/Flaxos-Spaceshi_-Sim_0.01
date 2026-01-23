const logPanel = document.getElementById("log");
const structuredLogPanel = document.getElementById("structured-log");
let latestUpdateInfo = null;

const actionButtons = new Map();
const cooldownState = {
  remaining: 0,
  total: 0,
  updatedAt: 0,
};

function appendLog(message, type = "info") {
  if (!logPanel) {
    return;
  }
  const item = document.createElement("div");
  item.className = `log-item ${type}`;
  item.textContent = message;
  logPanel.prepend(item);
}

function appendStructuredLog({ title, detail, type = "info" }) {
  if (!structuredLogPanel) {
    return;
  }
  const wrapper = document.createElement("div");
  wrapper.className = `structured-item ${type}`;

  const meta = document.createElement("div");
  meta.className = "meta";
  const label = document.createElement("span");
  label.textContent = title || "Event";
  const time = document.createElement("span");
  time.textContent = new Date().toLocaleTimeString();
  meta.append(label, time);

  const body = document.createElement("div");
  body.textContent = detail || "";

  wrapper.append(meta, body);
  structuredLogPanel.prepend(wrapper);
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

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  el.textContent = value ?? "--";
}

function setLed(id, level) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  el.classList.remove("ok", "warn", "critical", "offline");
  if (level) {
    el.classList.add(level);
  }
}

function formatNumber(value, decimals = 1) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(decimals);
}

function formatVector(vec, keys = ["x", "y", "z"], decimals = 1) {
  if (!vec) {
    return "--";
  }
  return keys
    .map((key) => `${key}:${formatNumber(vec[key], decimals)}`)
    .join(" ");
}

function magnitude(vec) {
  if (!vec) {
    return 0;
  }
  const x = Number(vec.x || 0);
  const y = Number(vec.y || 0);
  const z = Number(vec.z || 0);
  return Math.sqrt(x * x + y * y + z * z);
}

function summarizeResponse(response) {
  if (!response || typeof response !== "object") {
    return String(response);
  }
  if (response.error) {
    return `Error: ${response.error}`;
  }
  if (response.message) {
    return response.message;
  }
  if (response.ship && response.state) {
    return `State update for ${response.ship}`;
  }
  if (Array.isArray(response.ships)) {
    return `State update (${response.ships.length} ships)`;
  }
  return "Response received";
}

function extractShipState(response, shipId) {
  if (!response) {
    return null;
  }
  if (response.state) {
    return response.state;
  }
  const ships = response.ships;
  if (!ships) {
    return null;
  }
  const shipList = Array.isArray(ships) ? ships : Object.values(ships);
  if (shipList.length === 0) {
    return null;
  }
  if (shipId) {
    return shipList.find((ship) => ship.id === shipId) || shipList[0];
  }
  return shipList[0];
}

function updateShipStatus(state) {
  if (!state) {
    return;
  }
  const navSystem = state.systems?.navigation || {};
  const targetingSystem = state.systems?.targeting || {};
  const weaponsSystem = state.systems?.weapons || {};
  const sensorsSystem = state.systems?.sensors || {};
  const powerSystem = state.systems?.power || state.systems?.power_management || {};

  setText("ship-name", state.name || state.id);
  setText("ship-class", state.class || "--");
  setText("ship-position", formatVector(state.position));
  setText("ship-velocity", formatVector(state.velocity));
  setText("ship-nav-mode", navSystem.mode || (navSystem.autopilot_enabled ? "autopilot" : "manual"));

  const hullPercent = Number(state.hull_percent ?? 0);
  if (Number.isFinite(hullPercent)) {
    setText("ship-hull", `${formatNumber(hullPercent, 1)}%`);
    if (hullPercent > 60) {
      setLed("ship-hull-led", "ok");
    } else if (hullPercent > 30) {
      setLed("ship-hull-led", "warn");
    } else {
      setLed("ship-hull-led", "critical");
    }
  } else {
    setText("ship-hull", "--");
    setLed("ship-hull-led", "offline");
  }

  setText("nav-autopilot", navSystem.autopilot_enabled ? "Engaged" : "Manual");
  setLed("nav-autopilot-led", navSystem.autopilot_enabled ? "ok" : "offline");
  setText("nav-target-status", targetingSystem.locked_target || "--");
  setText("nav-thrust-status", formatVector(state.thrust));

  const weapons = weaponsSystem.weapons || [];
  if (Array.isArray(weapons) && weapons.length > 0) {
    const ready = weapons.filter((weapon) => weapon.can_fire).length;
    setText("tactical-weapons-status", `${ready}/${weapons.length} ready`);
    setLed("tactical-weapons-led", ready > 0 ? "ok" : "warn");
  } else {
    setText("tactical-weapons-status", "offline");
    setLed("tactical-weapons-led", "offline");
  }
  setText("tactical-locked-target", targetingSystem.locked_target || "--");

  if (powerSystem && typeof powerSystem === "object" && Object.keys(powerSystem).length > 0) {
    setText("power-status", powerSystem.status || "online");
    const percent = Number(powerSystem.percent ?? 0);
    if (Number.isFinite(percent)) {
      if (percent > 40) {
        setLed("power-status-led", "ok");
      } else if (percent > 15) {
        setLed("power-status-led", "warn");
      } else {
        setLed("power-status-led", "critical");
      }
    }
    if (Number.isFinite(powerSystem.stored_power) && Number.isFinite(powerSystem.capacity)) {
      setText(
        "power-stored",
        `${formatNumber(powerSystem.stored_power, 1)}/${formatNumber(powerSystem.capacity, 1)}`
      );
    } else {
      setText("power-stored", "--");
    }
    setText("power-draw", formatNumber(powerSystem.total_draw ?? 0, 1));
  } else {
    setText("power-status", "--");
    setLed("power-status-led", "offline");
    setText("power-stored", "--");
    setText("power-draw", "--");
  }

  const canPing = sensorsSystem.can_ping;
  if (typeof canPing === "boolean") {
    setText("sensor-ping-ready", canPing ? "Ready" : "Cooling");
    setLed("sensor-ping-led", canPing ? "ok" : "warn");
  } else {
    setText("sensor-ping-ready", "--");
    setLed("sensor-ping-led", "offline");
  }

  const contactCount = sensorsSystem.contact_count ?? sensorsSystem.contacts?.length ?? 0;
  setText("sensor-contact-count", `${contactCount}`);

  const cooldownRemaining = Number(sensorsSystem.ping_cooldown_remaining ?? 0);
  const cooldownTotal = Number(sensorsSystem.ping_cooldown_total ?? 0);
  updateCooldownState(cooldownRemaining, cooldownTotal);

  renderContacts(sensorsSystem.contacts || []);
}

function updateCooldownState(remaining, total) {
  if (!Number.isFinite(remaining) || remaining <= 0) {
    cooldownState.remaining = 0;
    cooldownState.total = total || 0;
    cooldownState.updatedAt = Date.now();
    setText("sensor-ping-cooldown", "0s");
    setActionCooldown("ping-sensors", false);
    return;
  }
  cooldownState.remaining = remaining;
  cooldownState.total = total || remaining;
  cooldownState.updatedAt = Date.now();
  setActionCooldown("ping-sensors", true);
}

function setActionCooldown(action, isCooling) {
  const button = actionButtons.get(action);
  if (!button) {
    return;
  }
  button.classList.toggle("action-cooldown", Boolean(isCooling));
}

function updateCooldownDisplay() {
  if (!cooldownState.updatedAt) {
    return;
  }
  const elapsed = (Date.now() - cooldownState.updatedAt) / 1000;
  const remaining = Math.max(0, cooldownState.remaining - elapsed);
  setText("sensor-ping-cooldown", `${formatNumber(remaining, 0)}s`);
  if (remaining <= 0) {
    setActionCooldown("ping-sensors", false);
  }
}

function renderContacts(contacts) {
  const list = document.getElementById("sensor-contacts");
  if (!list) {
    return;
  }
  list.innerHTML = "";
  if (!Array.isArray(contacts) || contacts.length === 0) {
    const empty = document.createElement("div");
    empty.className = "contact-row";
    empty.textContent = "No contacts detected.";
    list.appendChild(empty);
    return;
  }

  contacts.forEach((contact) => {
    const row = document.createElement("div");
    row.className = "contact-row";
    row.tabIndex = 0;

    const meta = document.createElement("div");
    meta.className = "contact-meta";
    const distance = formatNumber(contact.distance, 1);
    const bearing = formatNumber(contact.bearing, 1);
    const confidence = typeof contact.confidence === "number"
      ? `${formatNumber(contact.confidence * 100, 0)}%`
      : "--";
    const method = contact.detection_method || contact.detectionMethod || "unknown";
    meta.textContent = `${contact.id} | ${method} | D:${distance} | B:${bearing} | C:${confidence}`;

    const actions = document.createElement("div");
    actions.className = "contact-actions";

    const copyBtn = document.createElement("button");
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", () => copyContactId(contact.id));

    const tacticalBtn = document.createElement("button");
    tacticalBtn.textContent = "To Tactical";
    tacticalBtn.addEventListener("click", () => setInputValue("tactical-target", contact.id));

    const helmBtn = document.createElement("button");
    helmBtn.textContent = "To Helm";
    helmBtn.addEventListener("click", () => setInputValue("nav-target", contact.id));

    actions.append(copyBtn, tacticalBtn, helmBtn);
    row.append(meta, actions);

    row.addEventListener("click", (event) => {
      if (event.target && event.target.tagName === "BUTTON") {
        return;
      }
      copyContactId(contact.id);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        copyContactId(contact.id);
      }
    });

    list.appendChild(row);
  });
}

async function copyContactId(contactId) {
  if (!contactId) {
    return;
  }
  try {
    await navigator.clipboard.writeText(contactId);
    appendLog(`Copied contact ID: ${contactId}`, "info");
    appendStructuredLog({
      title: "Contact Copied",
      detail: contactId,
      type: "response",
    });
  } catch (error) {
    appendLog(`Copy failed: ${contactId}`, "error");
  }
}

function setInputValue(id, value) {
  const input = document.getElementById(id);
  if (!input) {
    return;
  }
  input.value = value;
  appendLog(`Set ${id} to ${value}`, "info");
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

async function sendCommand(command, extra = {}, options = {}) {
  const { host, port, ship } = getConnection();
  const payload = { cmd: command, ship, ...extra };

  if (!options.silent) {
    appendLog(`>> ${JSON.stringify(payload)}`, "request");
    appendStructuredLog({
      title: `Sent: ${command}`,
      detail: JSON.stringify(extra || {}),
      type: "request",
    });
  }

  try {
    const response = await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, port, payload }),
    });

    const data = await response.json();
    if (!data.ok) {
      if (!options.silent) {
        appendLog(`!! ${data.error}`, "error");
        appendStructuredLog({
          title: `Error: ${command}`,
          detail: data.error || "Unknown error",
          type: "error",
        });
      }
      return { ok: false, error: data.error, response: data.response };
    }

    if (!options.silent) {
      appendLog(`<< ${JSON.stringify(data.response)}`, "response");
      appendStructuredLog({
        title: `Response: ${command}`,
        detail: summarizeResponse(data.response),
        type: "response",
      });
    }
    return { ok: true, response: data.response };
  } catch (error) {
    if (!options.silent) {
      appendLog(`!! ${error}`, "error");
      appendStructuredLog({
        title: `Error: ${command}`,
        detail: String(error),
        type: "error",
      });
    }
    return { ok: false, error: String(error) };
  }
}

async function refreshState(silent = false) {
  const result = await sendCommand("get_state", {}, { silent });
  if (result?.ok) {
    const shipId = document.getElementById("ship")?.value?.trim();
    const state = extractShipState(result.response, shipId);
    updateShipStatus(state);
  }
  return result;
}

function ensureButtonIndicators() {
  document.querySelectorAll("button[data-action]").forEach((button) => {
    button.classList.add("action-button");
    if (!button.querySelector(".button-led")) {
      const led = document.createElement("span");
      led.className = "button-led";
      button.prepend(led);
    }
    if (button.dataset.action) {
      actionButtons.set(button.dataset.action, button);
    }
  });
}

function setButtonState(button, state) {
  if (!button) {
    return;
  }
  button.classList.remove("action-active", "action-success", "action-error");
  if (state) {
    button.classList.add(state);
  }
}

function flashButton(button) {
  setButtonState(button, "action-active");
  setTimeout(() => setButtonState(button, null), 350);
}

function showButtonResult(button, isOk) {
  setButtonState(button, isOk ? "action-success" : "action-error");
  setTimeout(() => setButtonState(button, null), 1200);
}

function setUpAdjustButtons() {
  document.querySelectorAll("button[data-adjust]").forEach((button) => {
    button.addEventListener("click", () => {
      const inputId = button.dataset.adjust;
      const step = Number(button.dataset.step || 0);
      const input = document.getElementById(inputId);
      if (!input) {
        return;
      }
      const current = Number(input.value || 0);
      const next = current + step;
      input.value = Math.max(input.min ? Number(input.min) : next, next);
      appendLog(`Adjusted ${inputId} to ${input.value}`, "info");
    });
  });
}

function setUpActions() {
  ensureButtonIndicators();
  setUpAdjustButtons();
  document.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      flashButton(button);

      if (action === "test-connection") {
        const result = await refreshState();
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "get-state") {
        const result = await refreshState();
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "set-thrust") {
        const result = await sendCommand("set_thrust", {
          x: Number(document.getElementById("thrust-x").value),
          y: Number(document.getElementById("thrust-y").value),
          z: Number(document.getElementById("thrust-z").value),
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "set-course") {
        const result = await sendCommand("set_course", {
          x: Number(document.getElementById("course-x").value),
          y: Number(document.getElementById("course-y").value),
          z: Number(document.getElementById("course-z").value),
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "set-autopilot") {
        const result = await sendCommand("autopilot", {
          enabled: document.getElementById("autopilot").value === "true",
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "set-target") {
        const result = await sendCommand("set_target", {
          target: document.getElementById("nav-target").value.trim(),
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "ping-sensors") {
        const result = await sendCommand("ping_sensors", {
          mode: document.getElementById("sensor-mode").value,
          count: Number(document.getElementById("sensor-count").value),
        });
        showButtonResult(button, result?.ok);
        if (result?.ok) {
          await refreshState(true);
        }
        return;
      }

      if (action === "fire-weapon") {
        const result = await sendCommand("fire_weapon", {
          target: document.getElementById("tactical-target").value.trim(),
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "toggle-system") {
        const result = await sendCommand("toggle_system", {
          system: document.getElementById("power-system").value.trim(),
          state: document.getElementById("power-state").checked ? 1 : 0,
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "set-power-allocation") {
        const result = await sendCommand("set_power_allocation", {
          primary: Number(document.getElementById("power-primary").value),
          secondary: Number(document.getElementById("power-secondary").value),
          tertiary: Number(document.getElementById("power-tertiary").value),
        });
        showButtonResult(button, result?.ok);
        return;
      }

      if (action === "check-update") {
        await checkForUpdates();
        showButtonResult(button, true);
        return;
      }

      if (action === "apply-update") {
        await applyUpdate();
        showButtonResult(button, true);
        return;
      }

      appendLog(`Unknown action: ${action}`, "error");
      showButtonResult(button, false);
    });
  });
}

// Initialize
setUpActions();
loadVersionInfo();
refreshState(true);
setInterval(updateCooldownDisplay, 500);

// Auto-check for updates on page load (optional, after 5 seconds)
setTimeout(() => {
  checkForUpdates();
}, 5000);
