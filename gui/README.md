# Flaxos Spaceship Sim - Legacy GUI

This directory contains the legacy web-components frontend.

The default frontend is the Svelte client in `gui-svelte/`, typically launched
with:

```bash
python tools/start_gui_stack.py --browser
```

Use the legacy UI only when you specifically want the old static client:

```bash
python tools/start_gui_stack.py --ui legacy --browser
```

## Architecture

```
Browser (GUI)  ←WebSocket→  ws_bridge.py  ←TCP→  Simulation Server
```

The legacy GUI connects to a WebSocket bridge that forwards commands to the
unified TCP simulation server.

## Quick Start

### One-Command Stack (Recommended)

From the repo root:

```bash
python tools/start_gui_stack.py --browser
```

This launches the default Svelte UI, the TCP simulation server, the WebSocket
bridge, and the GUI HTTP server.

To launch this legacy frontend instead:

```bash
python tools/start_gui_stack.py --ui legacy --browser
```

### Manual Setup

**1. Install Dependencies**

```bash
pip install websockets
```

**2. Start the Simulation Server**

```bash
python -m server.main --mode station --port 8765
```

**3. Start the WebSocket Bridge**

```bash
python gui/ws_bridge.py --tcp-port 8765 --ws-port 8081
```

**4. Open the Legacy GUI**

```bash
cd gui
python -m http.server 3100
# Then open http://localhost:3100
```

## Configuration

### WebSocket Bridge Options

```
--ws-host    WebSocket bind host (default: 0.0.0.0)
--ws-port    WebSocket port (default: 8081)
--tcp-host   TCP server host (default: 127.0.0.1)
--tcp-port   TCP server port (default: 8765)
--game-code  Shared secret for WS auth (recommended for remote access)
--allowed-origin-host  Optional browser Origin hostname allowlist entry
```

Default ports: TCP=8765, WS=8081, HTTP=3100

### GUI URL Parameters

- `?ws=ws://host:port` — Custom WebSocket URL
- `?noauto` — Disable auto-connect
- `?debug` — Enable debug logging

## Helm View — Glass Cockpit Layout

The Helm view uses a 3-column layout across 10 panels (consolidated from 14 in earlier builds).

```
┌─────────────────┬──────────────────────┬──────────────────┐
│  LEFT COLUMN    │   CENTER COLUMN      │  RIGHT COLUMN    │
│  Situational    │   Command &          │  Ship Status     │
│  Awareness      │   Control            │                  │
│                 │                      │                  │
│  Contacts       │  Flight Computer     │  Autopilot       │
│  Flight Data    │  Manual Flight       │  Status          │
│                 │  RCS / Attitude      │  Helm Queue      │
│                 │  Docking             │  Maneuver        │
│                 │                      │  Planner         │
└─────────────────┴──────────────────────┴──────────────────┘
                  [Helm Workflow Strip — full width]
```

### Panels

| # | Panel | Column | Role |
|---|-------|--------|------|
| 1 | Contacts | Left | Sensor contacts list — read-only awareness |
| 2 | Flight Data | Left | Position, velocity, delta-v — read-only; merged from nav + delta-v panels |
| 3 | Flight Computer | Center | Primary command panel; absorbs autopilot-control + set-course |
| 4 | Manual Flight | Center | Throttle + heading controls; merged from two separate panels |
| 5 | RCS / Attitude | Center | Fine attitude control |
| 6 | Autopilot Status | Right | Current autopilot program and phase — read-only |
| 7 | Helm Queue | Right | Delegation queue; absorbs helm-requests panel |
| 8 | Docking | Center | Docking approach and clamp controls |
| 9 | Maneuver Planner | Right | Expert trajectory tool; renamed from Flight Computer Local |
| 10 | Helm Workflow Strip | Full width | Breadcrumb showing current workflow step, tier-aware |

### Panel Attributes

Panels accept three standard attributes that drive visual hierarchy and state:

| Attribute | Values | Effect |
|-----------|--------|--------|
| `priority` | `primary`, `secondary`, `tertiary` | Raised background, border weight, and shadow depth |
| `domain` | `nav`, `sensor`, `helm`, `comms`, `weapons`, `power` | Color-coded left border accent |
| `disabled-reason` | Any string | Renders a disabled overlay on the panel with the provided explanation |

Example:
```html
<flaxos-panel title="Manual Flight" priority="primary" domain="helm"
              disabled-reason="Autopilot active — disengage to control manually">
```

Panel-group wrappers use `display: contents` so the inner panels participate directly in the CSS grid.

### CSS Utility Classes

These classes are available inside panel Shadow DOMs for consistent display of data:

| Class | Use |
|-------|-----|
| `.status-chip` | Inline status pill; combine with `.nominal`, `.warning`, `.critical`, `.offline`, `.info` |
| `.data-table-dense` | Compact monospace table for columnar readouts |
| `.kv-inline` | Key-value pair row — label left, value right |
| `.big-number` | Hero numeric display; use `.unit` as a child element for the unit label |
| `.panel-group` / `.panel-group-header` | Section dividers within a panel |

## Tier Visual Identity

The control tier selector sets `body.tier-{id}` and a `window.controlTier` string. Each tier has a distinct visual language and promotes different panels as the hero (largest grid span).

### RAW
- Accent: red. Font: monospace. Corners: sharp. Overlay: scanline effect.
- Hero panel: Manual Flight (8-column span).
- Shows: manual controls (throttle, heading, RCS). Hides: autopilot panels, helm queue.
- Audience: experienced pilots who want direct control.

### ARCADE
- Accent: blue. Font: mixed. Corners: rounded. Effect: blue glow.
- Hero panel: Flight Computer (6-column span).
- Shows: guided workflow panels. Hides: expert tools (Maneuver Planner).
- Audience: new players following a workflow.

### CPU-ASSIST
- Accent: purple. Font: sans-serif. Type size: larger.
- Hero panel: Autopilot Status (6-column span).
- Shows: status and delegation panels. Hides: all manual flight controls.
- Audience: captain-level oversight, autopilot does the flying.

Tier CSS lives in `gui/styles/tiers.css`. Use view-specific panel class selectors (`body.tier-raw .helm-manual-flight-panel`) rather than `:has()` for cross-browser reliability.

## File Structure

```
gui/
├── index.html                    # Main entry point
├── ws_bridge.py                  # WebSocket-TCP bridge
├── README.md                     # This file
├── styles/
│   ├── main.css                  # CSS foundation & variables
│   ├── tiers.css                 # Tier visual identity & panel visibility
│   └── mobile.css                # Mobile-specific overrides
├── js/
│   ├── main.js                   # App initialization
│   ├── ws-client.js              # WebSocket client
│   ├── state-manager.js          # State synchronization
│   ├── gestures.js               # Touch gesture handling
│   └── autopilot-utils.js        # Shared autopilot formatting & phase logic
└── components/
    ├── connection-status.js      # Connection indicator
    ├── panel.js                  # Collapsible panel container (priority/domain/disabled-reason)
    ├── event-log.js              # Scrolling event log
    ├── command-prompt.js         # Text command input
    ├── system-message.js         # Toast notifications
    ├── ship-status.js            # Hull/fuel/power display
    ├── flight-data-panel.js      # Position, velocity, delta-v (merged nav + delta-v)
    ├── flight-computer-panel.js  # Primary helm command panel (absorbs autopilot-control + set-course)
    ├── manual-flight-panel.js    # Throttle + heading (merged from two panels)
    ├── rcs-control.js            # Fine attitude control
    ├── autopilot-status.js       # Autopilot program & phase display (read-only)
    ├── helm-queue-panel.js       # Delegation queue (absorbs helm-requests)
    ├── docking-panel.js          # Docking approach & clamp controls
    ├── maneuver-planner.js       # Expert trajectory tool (renamed from flight-computer.js)
    ├── helm-workflow-strip.js    # Workflow breadcrumb strip
    ├── sensor-contacts.js        # Contact list & ping
    ├── targeting-display.js      # Target lock & solution
    ├── weapons-status.js         # Ammo & fire control
    ├── weapon-controls.js        # Fire/lock buttons
    ├── system-toggles.js         # System power toggles
    ├── scenario-loader.js        # Scenario list & load
    ├── mission-objectives.js     # Mission status & objectives
    ├── touch-throttle.js         # Mobile touch throttle
    └── touch-joystick.js         # Mobile virtual joystick
```

## Commands

The GUI sends JSON commands to the server:

```json
{"cmd": "command_name", "arg1": "value1", ...}
```

See `docs/FLIGHT-COMPUTER.md` for the full command reference.

## Testing

1. Start the simulation server
2. Start the WebSocket bridge
3. Open the GUI in a browser
4. Use the debug console to send test commands:
   - `{"cmd": "get_state"}` — Get ship state
   - `{"cmd": "contacts"}` — Get sensor contacts
   - `{"cmd": "ping"}` — Active sensor ping

Connection status indicator:
- CONNECTED — WebSocket connected
- CONNECTING — Attempting connection
- DISCONNECTED — Not connected

## Mobile Support

The GUI automatically switches to a mobile-optimized layout on screens <= 768px wide.

- Tab navigation: NAV, SEN, WPN, LOG, SYS
- Touch throttle: vertical drag with 10% snap increments
- Touch joystick: virtual pitch/yaw control
- Swipe left/right to change tabs
- iOS/Android safe area handling, touch targets >= 44px
