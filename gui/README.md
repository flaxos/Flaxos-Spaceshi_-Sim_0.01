# Flaxos Spaceship Sim - GUI

Web-based command interface for the Flaxos Spaceship Simulation.

## Architecture

```
Browser (GUI)  ←WebSocket→  ws_bridge.py  ←TCP→  Simulation Server
```

The GUI connects to a WebSocket bridge that forwards commands to the existing TCP simulation server.

## Quick Start

### One-Command Stack (Recommended)

From the repo root:

```bash
python tools/start_gui_stack.py --server station
```

This launches the TCP simulation server, WebSocket bridge, and GUI HTTP server.

### 1. Install Dependencies

```bash
pip install websockets
```

### 2. Start the Simulation Server

```bash
# Recommended: station-aware server (multi-crew / permissions)
python -m server.station_server --port 8765

# Minimal server (no stations)
# python -m server.run_server --port 8765
```

### 3. Start the WebSocket Bridge

```bash
python gui/ws_bridge.py --tcp-port 8765 --ws-port 8080
```

### 4. Open the GUI

Open `gui/index.html` in a browser, or serve it via a simple HTTP server:

```bash
# Python 3
cd gui
python -m http.server 3000
# Then open http://localhost:3000
```

## Configuration

### WebSocket Bridge Options

```
--ws-host    WebSocket bind host (default: 0.0.0.0)
--ws-port    WebSocket port (default: 8080)
--tcp-host   TCP server host (default: 127.0.0.1)
--tcp-port   TCP server port (default: 8765)
```

### GUI URL Parameters

- `?ws=ws://host:port` - Custom WebSocket URL
- `?noauto` - Disable auto-connect
- `?debug` - Enable debug logging

## Development Phases

The GUI is being developed in phases:

- **Phase 1**: Foundation & Transport (WebSocket bridge, connection UI) ✓
- **Phase 2**: Text Interface (event log, command prompt) ✓
- **Phase 3**: Status Displays (ship status, navigation, sensors, weapons) ✓
- **Phase 4**: Visual Controls (throttle, heading, autopilot) ✓
- **Phase 5**: Integration (layout, scenarios, missions) ✓
- **Phase 6**: Mobile Optimization (touch controls, responsive) ✓

## Mobile Support

The GUI automatically switches to a mobile-optimized layout on screens <= 768px wide.

### Mobile Features
- **Tab Navigation**: 5 tabs (NAV, SEN, WPN, LOG, SYS) for panel grouping
- **Touch Throttle**: Vertical drag control with 10% snap increments
- **Touch Joystick**: Virtual joystick for pitch/yaw control
- **Quick Actions**: Fire, Lock, Autopilot, Ping buttons
- **Swipe Gestures**: Swipe left/right to change tabs
- **iOS/Android Support**: Safe area handling, touch targets >= 44px

### Testing on Mobile
1. Ensure server is accessible on your network (`--host 0.0.0.0`)
2. Open `http://<server-ip>:3000` on your mobile device
3. See `docs/MOBILE_GUI_TESTING.md` for full testing checklist

## File Structure

```
gui/
├── index.html                # Main entry point
├── ws_bridge.py              # WebSocket-TCP bridge
├── README.md                 # This file
├── styles/
│   ├── main.css              # CSS foundation & variables
│   └── mobile.css            # Mobile-specific overrides
├── js/
│   ├── main.js               # App initialization
│   ├── ws-client.js          # WebSocket client
│   ├── state-manager.js      # State synchronization
│   └── gestures.js           # Touch gesture handling
├── components/
│   ├── connection-status.js  # Connection indicator
│   ├── panel.js              # Collapsible panel container
│   ├── event-log.js          # Scrolling event log
│   ├── command-prompt.js     # Text command input
│   ├── system-message.js     # Toast notifications
│   ├── ship-status.js        # Hull/fuel/power display
│   ├── navigation-display.js # Position/velocity/heading
│   ├── sensor-contacts.js    # Contact list & ping
│   ├── targeting-display.js  # Target lock & solution
│   ├── weapons-status.js     # Ammo & fire control
│   ├── throttle-control.js   # Vertical throttle slider
│   ├── heading-control.js    # Pitch/yaw controls
│   ├── autopilot-control.js  # Autopilot mode selector
│   ├── weapon-controls.js    # Fire/lock buttons
│   ├── system-toggles.js     # System power toggles
│   ├── quick-actions.js      # Quick action bar
│   ├── scenario-loader.js    # Scenario list & load
│   ├── mission-objectives.js # Mission status & objectives
│   ├── touch-throttle.js     # Mobile touch throttle (Phase 6)
│   └── touch-joystick.js     # Mobile virtual joystick (Phase 6)
└── layouts/
    └── mobile-layout.js      # Mobile tab layout (Phase 6)
```

## Commands

The GUI sends JSON commands to the server in the format:

```json
{"cmd": "command_name", "arg1": "value1", ...}
```

See `docs/GUI_DEV_PLAN.md` for the full command reference.

## Testing

1. Start the simulation server
2. Start the WebSocket bridge
3. Open the GUI in a browser
4. Use the debug console to send test commands:
   - `{"cmd": "get_state"}` - Get ship state
   - `{"cmd": "contacts"}` - Get sensor contacts
   - `{"cmd": "ping"}` - Active sensor ping

The connection status indicator should show:
- 🟢 CONNECTED - WebSocket connected
- 🟡 CONNECTING - Attempting connection
- ⚪ DISCONNECTED - Not connected
