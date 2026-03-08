# GUI Guide

## Overview

The web GUI connects to the simulation server via a WebSocket bridge and
provides a multi-view interface for commanding your ship.

Start the stack:
```bash
python tools/start_gui_stack.py
```
This launches the server, WebSocket bridge, and opens the GUI in a browser.

## Views

The interface is split into four tabbed views. Switch between them using the
tab bar or keyboard shortcuts.

### 1. Helm (key: `1`)

Primary piloting view. Contains:
- **Flight Computer** -- server-side manoeuvre commands (navigate, intercept,
  orbit, evasive, hold, abort)
- **Contacts** -- sensor contact list
- **Navigation** -- position, velocity, heading readouts
- **Autopilot** -- direct autopilot program selector
- **Autopilot Status** -- current autopilot phase and progress
- **Throttle / Heading / Set Course / RCS** -- manual flight controls
- **Flight Computer (Local)** -- client-side waypoint/flip-burn calculator
- **Helm Requests** -- inter-station request queue

### 2. Tactical (key: `2`)

Combat and situational awareness:
- **Sensors** -- full contact list with classification
- **Tactical Map** -- 2D overhead map of contacts
- **Targeting** -- lock pipeline and firing solution
- **Weapons** -- weapon status, ammo, hardpoints
- **Fire Control** -- fire buttons, weapon selection

### 3. Engineering (key: `3`)

Ship health and systems management:
- **Ship Status** -- hull integrity, subsystem health
- **Systems** -- power on/off toggles for each system
- **Power Management** -- reactor output, bus allocation, profiles
- **Navigation** -- duplicate nav readout for engineering reference
- **Event Log** -- scrollable event history
- **Position / Heading Calculator** -- manual nav math
- **Micro RCS / Debug Thrust** -- fine attitude and debug controls

### 4. Mission (key: `4`)

Scenario and command interface:
- **Scenarios** -- load/start scenario files
- **Mission** -- objectives and completion status
- **Command** -- text command prompt (CLI in the browser)
- **Event Log** -- mission-relevant events

## Keyboard Shortcuts

| Key        | Action                              |
|------------|-------------------------------------|
| `1`        | Switch to Helm view                 |
| `2`        | Switch to Tactical view             |
| `3`        | Switch to Engineering view          |
| `4`        | Switch to Mission view              |
| `H`        | Hold position (flight computer)     |
| `M`        | Manual override (flight computer)   |
| `Escape`   | Abort current command / close input |
| `T`        | Cycle target selection              |
| `F`        | Fire selected weapon                |
| `Ctrl+Shift+D` | Toggle debug logging           |

## Using the Flight Computer from the GUI

The flight computer panel is in the **Helm** view (top-left).

1. **Navigate** -- Click "Navigate", enter X/Y/Z coordinates, click "Navigate".
2. **Intercept / Match Vel** -- Click the button, select a contact from the
   dropdown, and the command fires automatically.
3. **Hold / Orbit / Evasive** -- Single click sends the command immediately.
4. **Manual** -- Disengages the flight computer for manual piloting.
5. **Abort** -- Emergency stop. Kills thrust and disengages autopilot.

The panel shows:
- Current **mode** (IDLE / EXECUTING / MANUAL)
- Active **command** and **phase**
- **Progress bar** with ETA
- **Burn plan** details (delta-v, fuel cost, confidence)

## Status Bar

The always-visible status bar at the top shows:
- Hull integrity (with color coding)
- Subsystem status dots (propulsion, sensors, weapons, navigation, power)
- Fuel level
- Ammo summary (torpedoes + PDC rounds)
- Current velocity

Color coding: green = nominal, yellow = impaired, red = critical.