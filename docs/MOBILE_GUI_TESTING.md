# Mobile GUI Testing Checklist

This is the current mobile checklist for the default Svelte bridge UI in `gui-svelte/`.

For the full mission ladder, use [UAT_MASTER_PLAN.md](/home/flax/games/spaceship-sim/docs/UAT_MASTER_PLAN.md). This document focuses on mobile layout quality, touch access, and on-device operability.

## Startup

Recommended:

```bash
python3 tools/start_gui_stack.py --lan --browser --rcon-password 'replace-this'
python3 tools/uat_monitor.py --follow --fail-on-critical
```

Device/browser targets:
- Android Chrome
- Android WebView / Pydroid browser if used in practice
- iPhone Safari
- iPhone Chrome

## Pass Order

Run these in order on each device:

1. Shell + auth
2. `Tutorial: Intercept and Dock`
3. `Combat: Eliminate Threat`
4. `Damage Control`

Stop if any scenario causes:
- GUI crash or reload
- repeated disconnect/reconnect
- invisible or untappable controls
- critical log output in `tools/uat_monitor.py`

## 1. Shell + Auth

### Layout

Check:
- page loads without console errors
- status bar remains readable
- station selector opens and closes cleanly
- tier selector remains usable
- view tabs remain tappable and horizontally scrollable if needed
- `Config` view is reachable without accidental mis-taps

### Server Admin

Open `Config > Server`.

Check:
- auth form is usable on a phone keyboard
- `Unlock` works
- stats cards stack cleanly
- pause/resume, time-scale, reset, and client actions remain tappable
- no clipped inputs or off-screen action buttons

Observe:
- server status refreshes every few seconds
- no stale session banner after successful auth

## 2. Helm Mobile Pass

Scenario:
- `01_tutorial_intercept.yaml`

Check:
- flight data panel fits vertically without broken overflow
- contacts remain selectable
- flight computer controls remain tappable
- manual controls are still usable after scrolling
- docking panel remains reachable after a long scroll

Expected:
- manual throttle still changes speed
- rendezvous/autopilot still closes range
- docking can be completed without rotating the device

## 3. Tactical Mobile Pass

Scenario:
- `02_combat_destroy.yaml`

Check:
- map renders without overlapping the rest of the tactical stack
- contact list rows remain tappable
- lock / fire controls remain reachable
- weapons status and combat log remain visible after scrolling
- no tactical panel disappears solely because it is secondary or tertiary priority

Expected:
- target lock and shot flow complete on mobile
- combat log still updates while scrolling the page

## 4. Ops / Engineering Mobile Pass

Scenario:
- `22_damage_control.yaml`

Check:
- subsystem status is legible at mobile width
- ops / engineering control buttons remain large enough to tap reliably
- event log or repair feedback remains reachable
- switching between `Ops`, `Engineering`, and `Config` does not lose scroll state or stall telemetry

Expected:
- repair/damage actions change visible state
- no clipped cards or frozen panels

## Touch Target Checklist

Check:
- critical buttons are comfortably tappable
- text inputs do not get hidden behind the virtual keyboard
- no control requires hover to reveal its only action
- panels scroll naturally without trapping touch interaction

## Orientation Checklist

Portrait:
- bridge chrome remains readable
- single-column layouts do not clip
- no critical controls are pushed below unusable heights

Landscape:
- tabs and station controls remain reachable
- mission/admin controls do not overflow off-screen

## Log Signals During Mobile UAT

Good signals:
- `Loaded scenario: ...`
- `RCON authenticated`
- `Client connected:`
- `Mission SUCCESS`

Bad signals:
- `Traceback`
- `ERROR`
- `subprocess exited unexpectedly`
- repeated `Client disconnected`
- repeated auth failures while the UI still appears connected

## Reporting

Record:
1. device + OS
2. browser
3. scenario
4. exact view/station
5. screenshot or short screen recording
6. matching `tools/uat_monitor.py` lines
