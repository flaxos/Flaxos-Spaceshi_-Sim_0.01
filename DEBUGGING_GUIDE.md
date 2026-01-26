# Debugging Guide - Navigation & Helm Controls

## Quick Diagnostic Commands

Open browser console (F12) and run these:

### 1. Check Current State
```javascript
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
console.log("Ship state:", state);
console.log("Throttle:", state.state?.systems?.propulsion?.throttle);
console.log("Flight path:", state.state?.flight_path);
console.log("Navigation:", state.state?.navigation);
```

### 2. Test Thrust Command Directly
```javascript
const response = await wsClient.sendShipCommand("set_thrust", {thrust: 0.5});
console.log("Response:", response);
// Should show: {ok: true, response: {status: "...", throttle: 0.5, ...}}
```

### 3. Test Heading Command Directly
```javascript
const response = await wsClient.sendShipCommand("set_orientation", {
  pitch: 10, 
  yaw: 45, 
  roll: 0
});
console.log("Response:", response);
// Should show: {ok: true, response: {status: "...", target: {...}}}
```

### 4. Check System Status
```javascript
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
const systems = state.state?.systems || {};
console.log("Propulsion enabled:", systems.propulsion?.enabled);
console.log("Helm enabled:", systems.helm?.enabled);
console.log("RCS enabled:", systems.rcs?.enabled);
console.log("Helm manual_override:", systems.helm?.manual_override);
console.log("Nav autopilot:", systems.navigation?.autopilot_enabled);
```

### 5. Test Micro RCS
```javascript
// Fire X-axis (roll) for 2 seconds
await wsClient.sendShipCommand("set_angular_velocity", {
  pitch: 0,
  yaw: 0,
  roll: 30  // 30 deg/s
});
// Wait 2 seconds, then stop
setTimeout(() => {
  wsClient.sendShipCommand("set_angular_velocity", {
    pitch: 0,
    yaw: 0,
    roll: 0
  });
}, 2000);
```

### 6. Test Point At
```javascript
// Point at absolute position
await wsClient.sendShipCommand("point_at", {
  position: {x: 1000, y: 2000, z: 0}
});
```

### 7. Test Flight Path
```javascript
// Move ship first, then check
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
const path = state.state?.flight_path || [];
console.log("Flight path samples:", path.length);
console.log("First position:", path[0]);
console.log("Last position:", path[path.length - 1]);
```

## Common Issues

### Sliders Not Working

**Check 1: System Enabled**
```javascript
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
console.log("Propulsion enabled:", state.state?.systems?.propulsion?.enabled);
// If false, propulsion system is disabled
```

**Check 2: Helm Manual Override**
```javascript
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
console.log("Helm manual_override:", state.state?.systems?.helm?.manual_override);
// If true, may need to disable: wsClient.sendShipCommand("helm_override", {enabled: false})
```

**Check 3: Autopilot Active**
```javascript
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
console.log("Autopilot enabled:", state.state?.systems?.navigation?.autopilot_enabled);
// If true, may need to disable autopilot first
```

**Check 4: Command Response**
```javascript
// Move slider and check console
// Should see: "Setting throttle: 0.5"
// Then: "Throttle response: {ok: true, response: {...}}"
// If you see errors, check the error message
```

### Components Not Visible

**Check 1: Component Registration**
```javascript
// In console:
customElements.get("micro-rcs-control");
// Should return: class MicroRCSControl
customElements.get("position-heading-calculator");
// Should return: class PositionHeadingCalculator
```

**Check 2: Panel Visibility**
- Look for "Micro RCS" panel in GUI (may be collapsed)
- Look for "Position → Heading" panel in GUI (may be collapsed)
- Check browser console for import errors

### Flight Path Empty

**Check 1: Ship Moving**
```javascript
// Ship must be moving (velocity > 0 or acceleration > 0)
const state = await wsClient.send("get_state", {
  ship: window._flaxosModules.stateManager.getPlayerShipId()
});
const vel = state.state?.velocity || {};
const speed = Math.sqrt(vel.x**2 + vel.y**2 + vel.z**2);
console.log("Ship speed:", speed, "m/s");
// If 0, ship isn't moving - flight path won't record
```

**Check 2: Simulation Running**
```javascript
// Check if simulation is running
// Flight path only records when ship.tick() is called
```

## Expected Response Formats

### set_thrust Response
```json
{
  "ok": true,
  "response": {
    "status": "Throttle updated",
    "throttle": 0.5,
    "thrust_magnitude": 50.0
  }
}
```

### set_orientation Response
```json
{
  "ok": true,
  "response": {
    "status": "Attitude target set (RCS will maneuver)",
    "target": {
      "pitch": 10.0,
      "yaw": 45.0,
      "roll": 0.0
    },
    "rcs_response": {...}
  }
}
```

## Force Enable Systems (If Disabled)

```javascript
// Enable propulsion
await wsClient.sendShipCommand("power_on", {system: "propulsion"});

// Enable helm
await wsClient.sendShipCommand("power_on", {system: "helm"});

// Enable RCS
await wsClient.sendShipCommand("power_on", {system: "rcs"});

// Disable helm manual override (if blocking)
await wsClient.sendShipCommand("helm_override", {enabled: false});

// Disable autopilot (if blocking)
await wsClient.sendShipCommand("autopilot", {enabled: false});
```
