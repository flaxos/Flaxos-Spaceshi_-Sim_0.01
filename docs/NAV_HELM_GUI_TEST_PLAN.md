# Navigation + Helm GUI Test Plan

This plan captures repeatable GUI checks and supporting scripts for validating navigation and helm flows, with a focus on the intercept tutorial scenario (`scenarios/01_tutorial_intercept.yaml`).

## Prerequisites
- Start the GUI stack: `python tools/start_gui_stack.py`
- Open the GUI: http://localhost:3000/
- Ensure the scenario is loaded from the scenario panel (Tutorial: Intercept and Approach).

## Manual GUI Test Cases

### NAV-HEL-01: Scenario load + telemetry sanity
**Goal:** Confirm the nav/helm stations receive telemetry without crashing.

1. Open the Scenario panel and load **Tutorial: Intercept and Approach**.
2. Switch to the **Helm** station.
3. Confirm Navigation panel shows position/velocity/heading data.
4. Switch to **Navigation** station and confirm the contacts list is populated after a sensors ping.

**Expected:**
- No server disconnects or JSON serialization errors.
- Navigation panel updates at least once per second.

---

### NAV-HEL-02: Autopilot intercept (C001)
**Goal:** Engage intercept autopilot on the tutorial contact.

1. In Navigation station, click **Ping Sensors**.
2. Select the contact `C001` (Tycho Station) from the contacts list.
3. Switch to Helm station.
4. Engage autopilot with program **Intercept**.
5. Observe autopilot status updates (Intercept → Approach → Match).

**Expected:**
- Autopilot engages without crashing the server.
- Navigation display shows target range closing.
- Autopilot phase changes appear in the event log.

---

### NAV-HEL-03: Manual helm override + recovery
**Goal:** Validate manual overrides don't break autopilot or JSON telemetry.

1. With autopilot engaged, use **Manual Thrust** to adjust throttle.
2. Rotate heading using Helm controls.
3. Wait for autopilot to resume (manual override timeout).

**Expected:**
- Manual input triggers override and then returns to autopilot.
- No disconnects or UI freeze during transition.

---

### NAV-HEL-04: Autopilot disengage
**Goal:** Verify the "off" command safely disables autopilot.

1. With autopilot engaged, send **Autopilot Off** from Helm.
2. Verify the ship returns to manual mode.

**Expected:**
- Autopilot status shows disabled.
- Helm controls regain manual authority with no crash.

---

### NAV-HEL-05: Station switching stress
**Goal:** Ensure switching between Helm and Navigation panels does not break telemetry.

1. Rapidly switch between Helm and Navigation stations 10 times.
2. Keep the ship in motion and verify the telemetry continues updating.

**Expected:**
- No station claim errors.
- Telemetry updates continue without server disconnects.

## Scripted Checks (Optional but Recommended)

Run the CLI-based validation script to confirm that navigation/helm commands respond with JSON-safe payloads while the GUI is open:

```bash
python tools/validate_nav_helm.py --scenario 01_tutorial_intercept.yaml
```

**Expected:**
- Script reports success for sensor ping and autopilot intercept.
- No `TypeError: Object of type bool is not JSON serializable` in server output.
