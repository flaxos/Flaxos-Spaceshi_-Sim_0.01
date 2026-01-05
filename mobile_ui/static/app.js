const logPanel = document.getElementById("log");

function appendLog(message, type = "info") {
  const item = document.createElement("div");
  item.className = `log-item ${type}`;
  item.textContent = message;
  logPanel.prepend(item);
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

      appendLog(`Unknown action: ${action}`, "error");
    });
  });
}

setUpActions();
