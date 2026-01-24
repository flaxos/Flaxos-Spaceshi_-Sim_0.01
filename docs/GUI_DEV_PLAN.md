# Flaxos Spaceship Sim — GUI Development Plan v1.0

## Document Purpose

This document defines a **structured, scope-locked GUI development roadmap** for AI agents to follow. The goal is a **1:1 feature-complete web interface** that exposes all existing simulation systems for practical testing of demo scenarios.

**CRITICAL RULES FOR AI AGENTS:**
1. NO new gameplay features — only GUI representation of existing systems
2. NO scope expansion beyond what's documented here
3. Each phase must be completed and tested before moving to next
4. All components must reference existing server API commands
5. If a feature isn't in this document, it's OUT OF SCOPE

---

## Architecture Overview
```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Web/Android)                      │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: VISUAL CONTROLS                                       │
│  ├── Throttle Slider, Heading Dial, System Toggles              │
│  ├── Weapon Controls, Target Lock Button                        │
│  └── Autopilot Mode Selector                                    │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: STATUS DISPLAYS                                       │
│  ├── Ship Status Panel (fuel, power, systems)                   │
│  ├── Navigation Display (position, velocity, heading)           │
│  ├── Sensor Contacts List                                       │
│  ├── Targeting Computer Display                                 │
│  └── Weapons Status Panel                                       │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: TEXT INTERFACE                                        │
│  ├── Event Log (scrolling feed)                                 │
│  ├── Command Prompt (direct text input)                         │
│  └── System Messages / Warnings                                 │
├─────────────────────────────────────────────────────────────────┤
│  TRANSPORT: WebSocket ↔ TCP JSON Bridge                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SERVER (Python/Existing)                      │
│  ├── TCP JSON API (port 8765)                                   │
│  ├── Simulation Loop                                            │
│  └── Fleet State Management                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Design Language: "Utilitarian Spacecraft Interface"

**Visual Philosophy** (Expanse-inspired, no IP):
- Dark background (#0a0a0f) with muted accent colors
- Monospace fonts for data (JetBrains Mono, Fira Code)
- Sans-serif for labels (Inter, system-ui)
- Color coding: 
  - Green (#00ff88) = nominal/active
  - Amber (#ffaa00) = warning/standby
  - Red (#ff4444) = critical/alert
  - Cyan (#00aaff) = information/sensor data
  - White (#e0e0e0) = neutral text
- Subtle borders, no gradients, minimal shadows
- Grid-based layout with clear visual hierarchy
- Status indicators use filled/empty circles or bars, not fancy animations

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Frontend Framework | **Vanilla JS + Web Components** | No build step, works in Pydroid WebView |
| Styling | **CSS Custom Properties** | Theming, no preprocessor needed |
| Transport | **WebSocket** | Real-time bidirectional |
| Bridge | **Python WebSocket ↔ TCP** | Existing server uses TCP JSON |
| Mobile | **Same codebase** | Responsive CSS, touch targets |
| Build | **None** | Single HTML + JS files |

**Why not React/Vue?** Build complexity breaks Pydroid compatibility and adds unnecessary dependencies for a simulation UI.

---

## Phase Structure
```
PHASE 1: Foundation & Transport Layer
    └── WebSocket bridge, basic connection UI
    
PHASE 2: Layer 1 — Text Interface
    └── Event log, command prompt, message display
    
PHASE 3: Layer 2 — Status Displays  
    └── All read-only status panels
    
PHASE 4: Layer 3 — Visual Controls
    └── All interactive controls (throttle, heading, etc.)
    
PHASE 5: Integration & Scenarios
    └── Scenario loader, mission objectives display
    
PHASE 6: Mobile Optimization
    └── Touch controls, responsive layout, Pydroid testing
```

---

# PHASE 1: Foundation & Transport Layer

## Objective
Establish reliable bidirectional communication between web client and simulation server.

## Deliverables

### 1.1 WebSocket-TCP Bridge (Python)
**File:** `gui/ws_bridge.py`
```python
# Specification only — implementation by agent

class WSBridge:
    """
    Bridges WebSocket clients to TCP simulation server.
    
    Responsibilities:
    - Accept WebSocket connections on configurable port (default: 8080)
    - Forward JSON messages to TCP server (default: localhost:8765)
    - Broadcast server responses to all connected WebSocket clients
    - Handle connection lifecycle (connect, disconnect, reconnect)
    
    Message Format (unchanged from existing):
    - Client → Server: {"cmd": "command_name", "args": {...}}
    - Server → Client: {"type": "state|event|error", "data": {...}}
    
    Error Handling:
    - TCP disconnect: notify all WS clients, attempt reconnect
    - WS disconnect: clean up client, continue serving others
    - Invalid JSON: log and ignore, don't crash
    """
```

### 1.2 Connection Status Component
**File:** `gui/components/connection-status.js`
```
┌─────────────────────────────────────┐
│ ● CONNECTED  Server: 192.168.1.20  │  ← Green dot when connected
│ ○ DISCONNECTED                      │  ← Empty circle when disconnected
│ ◐ CONNECTING...                     │  ← Half-filled when attempting
└─────────────────────────────────────┘

Properties:
- server_host: string
- server_port: number
- status: 'connected' | 'disconnected' | 'connecting'
- latency_ms: number (optional ping display)
```

### 1.3 Basic HTML Shell
**File:** `gui/index.html`
```html
<!-- Minimal structure — details in implementation -->
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="styles/main.css">
</head>
<body>
  <div id="app">
    <header id="connection-bar"></header>
    <main id="interface-grid">
      <!-- Panels injected by components -->
    </main>
  </div>
  <script type="module" src="js/main.js"></script>
</body>
</html>
```

### 1.4 CSS Foundation
**File:** `gui/styles/main.css`
```css
/* Define all CSS custom properties here */
:root {
  /* Colors */
  --bg-primary: #0a0a0f;
  --bg-panel: #12121a;
  --bg-input: #1a1a24;
  --border-default: #2a2a3a;
  --border-active: #3a3a4a;
  
  --text-primary: #e0e0e0;
  --text-secondary: #888899;
  --text-dim: #555566;
  
  --status-nominal: #00ff88;
  --status-warning: #ffaa00;
  --status-critical: #ff4444;
  --status-info: #00aaff;
  
  /* Typography */
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-sans: 'Inter', system-ui, sans-serif;
  
  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  
  /* Touch targets (mobile) */
  --touch-min: 44px;
}
```

## Phase 1 Acceptance Criteria

- [ ] Bridge starts and accepts WebSocket connections
- [ ] Bridge forwards messages to TCP server
- [ ] Bridge broadcasts responses to all WS clients
- [ ] Connection status component shows current state
- [ ] HTML shell loads without errors
- [ ] CSS variables are defined and applied
- [ ] Manual test: send `{"cmd": "get_state"}` via browser console, receive response

---

# PHASE 2: Layer 1 — Text Interface

## Objective
Implement the foundational text-based interface layer: event log, command prompt, and system messages.

## Deliverables

### 2.1 Event Log Component
**File:** `gui/components/event-log.js`
```
┌─ EVENT LOG ─────────────────────────────────────────┐
│ 14:32:01 [NAV] Autopilot engaged: INTERCEPT C001    │
│ 14:32:03 [SEN] Contact C002 detected bearing 045    │
│ 14:32:05 [WPN] Torpedo away — tracking C001         │
│ 14:32:07 [WPN] PDC engaged — 3 rounds expended      │
│ 14:32:09 [SYS] Warning: Fuel below 25%              │
│ ▼ (auto-scroll indicator)                           │
└─────────────────────────────────────────────────────┘

Features:
- Scrolling log with timestamp prefix
- Category tags: [NAV] [SEN] [WPN] [SYS] [COM] [ERR]
- Color coding by category/severity
- Max 500 entries (FIFO)
- Auto-scroll toggle
- Click to pause scroll, resume on new critical event

API Events to Display:
- All events from get_events response
- Connection status changes
- Command acknowledgments
```

### 2.2 Command Prompt Component
**File:** `gui/components/command-prompt.js`
```
┌─ COMMAND ───────────────────────────────────────────┐
│ > autopilot intercept C001_                         │
│                                                     │
│ History: ↑/↓  |  Tab: autocomplete  |  Enter: send │
└─────────────────────────────────────────────────────┘

Features:
- Text input with monospace font
- Command history (↑/↓ arrows), persisted in localStorage
- Basic autocomplete for known commands (Tab key)
- Submit on Enter
- Clear with Escape
- Visual feedback on command success/failure

Supported Commands (from existing API):
- get_state [ship_id]
- list_scenarios
- load_scenario <scenario_id>
- get_mission
- get_mission_hints
- pause
- set_thrust <0.0-1.0>
- set_thrust_vector <x> <y> <z> (debug)
- set_orientation <pitch> <yaw> <roll>
- set_angular_velocity <pitch_rate> <yaw_rate> <roll_rate>
- rotate <axis> <amount>
- ping_sensors
- lock_target <contact_id>
- unlock_target
- autopilot <program> [target]
- fire_weapon <weapon>
```

### 2.3 System Message Component
**File:** `gui/components/system-message.js`
```
┌─────────────────────────────────────────────────────┐
│ ⚠ WARNING: COLLISION COURSE — TCA 45s — CPA 2.3km  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ ✓ Autopilot: MATCH VELOCITY complete               │
└─────────────────────────────────────────────────────┘

Features:
- Toast-style notifications
- Auto-dismiss after 5s (configurable)
- Manual dismiss with click
- Stack up to 3, oldest dismissed first
- Priority levels: info, success, warning, critical
- Critical messages don't auto-dismiss
```

### 2.4 Panel Container Component
**File:** `gui/components/panel.js`
```
┌─ PANEL TITLE ───────────────────────────────────────┐
│                                                     │
│  (content slot)                                     │
│                                                     │
└─────────────────────────────────────────────────────┘

Features:
- Consistent header styling
- Optional collapse/expand
- Optional minimize button
- Slot for arbitrary content
- Standardized border and padding
```

## Phase 2 Acceptance Criteria

- [ ] Event log displays incoming events with timestamps
- [ ] Event log auto-scrolls, can be paused
- [ ] Event log color-codes by category
- [ ] Command prompt accepts text input
- [ ] Command prompt sends commands to server
- [ ] Command prompt shows history with arrow keys
- [ ] System messages appear for warnings/errors
- [ ] Panels have consistent styling
- [ ] Manual test: type `status` in prompt, see response in log

---

# PHASE 3: Layer 2 — Status Displays

## Objective
Implement all read-only status display panels that show current ship state.

## Deliverables

### 3.1 Ship Status Panel
**File:** `gui/components/ship-status.js`
```
┌─ SHIP STATUS ───────────────────────────────────────┐
│                                                     │
│  HULL         ████████████████████  100%           │
│  FUEL         ████████████░░░░░░░░   62%  4,280 kg │
│  POWER        ████████████████████  100%           │
│                                                     │
│  SYSTEMS                                            │
│  ├─ Propulsion    ● ONLINE                         │
│  ├─ Sensors       ● ONLINE                         │
│  ├─ Weapons       ● ONLINE                         │
│  ├─ Navigation    ● ONLINE                         │
│  └─ Comms         ○ OFFLINE                        │
│                                                     │
│  MASS: 45,000 kg    Δv: 2,340 m/s remaining        │
└─────────────────────────────────────────────────────┘

Data Source: get_state response
Fields:
- hull_integrity (if available, else omit)
- fuel_mass, fuel_capacity
- power_level
- systems_status (dict of system: online/offline)
- mass
- delta_v (calculated from fuel and mass)
```

### 3.2 Navigation Display
**File:** `gui/components/navigation-display.js`
```
┌─ NAVIGATION ────────────────────────────────────────┐
│                                                     │
│  POSITION                                           │
│  X:   +12,450.3 km                                  │
│  Y:    -3,220.1 km                                  │
│  Z:      +892.5 km                                  │
│                                                     │
│  VELOCITY                        HEADING            │
│  VX:   +245.2 m/s               PITCH:  +12.5°     │
│  VY:    -82.1 m/s               YAW:   +045.0°     │
│  VZ:    +15.3 m/s                                  │
│  ───────────────                                   │
│  MAG:   261.4 m/s                                  │
│                                                     │
│  THRUST: ████████░░  80%                           │
│                                                     │
│  AUTOPILOT: INTERCEPT C001                         │
│  Phase: APPROACH  |  Range: 12.4 km                │
└─────────────────────────────────────────────────────┘

Data Source: get_state response
Fields:
- position [x, y, z]
- velocity [vx, vy, vz]
- heading [pitch, yaw]
- thrust_level
- autopilot_mode
- autopilot_target
- autopilot_phase (if applicable)
```

### 3.3 Sensor Contacts Panel
**File:** `gui/components/sensor-contacts.js`
```
┌─ SENSOR CONTACTS ───────────────────────────────────┐
│                                                     │
│  ACTIVE PING: ░░░░░░░░░░ READY (cooldown: 0s)      │
│  PASSIVE:     ● SCANNING                           │
│                                                     │
│  ID     CLASS      BEARING  RANGE    CLOSURE       │
│  ────────────────────────────────────────────────  │
│ ►C001   FRIGATE    045°     12.4 km   -245 m/s    │ ← selected
│  C002   UNKNOWN    180°     54.2 km    +12 m/s    │
│  C003   SMALL      270°     8.1 km    -892 m/s    │
│                                                     │
│  Confidence: ████████░░ 78%                        │
│  Last Update: 2.3s ago                             │
│                                                     │
│  ○ No contacts in range                            │ ← empty state
└─────────────────────────────────────────────────────┘

Data Source: contacts command response
Fields per contact:
- contact_id
- classification
- bearing
- range
- range_rate (closure speed)
- confidence
- last_updated

Interaction:
- Click row to select (for targeting)
- Selected contact highlighted
- Sorted by range (nearest first)
```

### 3.4 Targeting Computer Display
**File:** `gui/components/targeting-display.js`
```
┌─ TARGETING ─────────────────────────────────────────┐
│                                                     │
│  ○ NO TARGET LOCK                                  │ ← no lock state
│                                                     │
│  ──────────────────────────────────────────────    │
│                                                     │
│  ◉ TARGET LOCKED: C001                             │ ← locked state
│                                                     │
│  CLASS:     FRIGATE (Corvette-class)               │
│  BEARING:   045.2°                                 │
│  RANGE:     12,450 m                               │
│  CLOSURE:   -245 m/s (CLOSING)                     │
│                                                     │
│  FIRING SOLUTION                                    │
│  TCA:       51s                                    │
│  CPA:       2,340 m                                │
│  LOCK:      ████████████████  92%                  │
│                                                     │
│  ⚠ COLLISION COURSE                                │ ← warning if applicable
└─────────────────────────────────────────────────────┘

Data Source: targeting state from get_state
Fields:
- target_locked: bool
- target_id
- target_class
- bearing
- range
- range_rate
- tca (time to closest approach)
- cpa (closest point of approach)
- lock_quality
- collision_warning
```

### 3.5 Weapons Status Panel
**File:** `gui/components/weapons-status.js`
```
┌─ WEAPONS ───────────────────────────────────────────┐
│                                                     │
│  TORPEDOES                                          │
│  ├─ Loaded:   ██████████░░  10/12                  │
│  ├─ Status:   ● READY                              │
│  └─ In Flight: 2                                   │
│                                                     │
│  PDC (Point Defense)                               │
│  ├─ Ammo:     ████████████████████  980/1000      │
│  ├─ Status:   ● TRACKING                          │
│  └─ Targets:  1 engaged                            │
│                                                     │
│  FIRE CONTROL: ● WEAPONS FREE                      │
│               ○ WEAPONS HOLD                       │
└─────────────────────────────────────────────────────┘

Data Source: get_state weapons section
Fields:
- torpedo_count, torpedo_max
- torpedo_status (ready/reloading/empty)
- torpedoes_in_flight
- pdc_ammo, pdc_max
- pdc_status (ready/tracking/firing/offline)
- pdc_targets_engaged
- fire_control_mode
```

## Phase 3 Acceptance Criteria

- [ ] Ship status shows fuel, power, systems
- [ ] Navigation display shows position, velocity, heading
- [ ] Navigation display shows autopilot status
- [ ] Sensor contacts list populates from server
- [ ] Contacts can be selected by clicking
- [ ] Targeting display shows lock status
- [ ] Targeting display shows firing solution when locked
- [ ] Weapons status shows ammo counts
- [ ] All displays update in real-time (polling or push)
- [ ] Manual test: all panels reflect server state correctly

---

# PHASE 4: Layer 3 — Visual Controls

## Objective
Implement all interactive controls that send commands to the server.

## Deliverables

### 4.1 Throttle Control
**File:** `gui/components/throttle-control.js`
```
┌─ THROTTLE ──────────────────┐
│                             │
│         ┌─────┐             │
│    100% │     │             │
│         │ ▓▓▓ │             │
│     80% │ ▓▓▓ │ ← current   │
│         │ ▓▓▓ │             │
│     60% │ ▓▓▓ │             │
│         │ ▓▓▓ │             │
│     40% │ ▓▓▓ │             │
│         │ ░░░ │             │
│     20% │ ░░░ │             │
│         │ ░░░ │             │
│      0% │     │             │
│         └─────┘             │
│                             │
│  [STOP] Current: 80%        │
└─────────────────────────────┘

Behavior:
- Vertical slider (drag or click)
- Discrete steps: 0, 10, 20, ..., 100%
- Emergency stop button (sends emergency_stop)
- Shows current value
- Sends: thrust <value>
- Touch-friendly: large drag target
```

### 4.2 Heading Control
**File:** `gui/components/heading-control.js`
```
┌─ HEADING ───────────────────────────────────────────┐
│                                                     │
│        PITCH                    YAW                 │
│          ▲                                          │
│          │                    ┌───┐                 │
│    ┌─────┼─────┐              │   │                 │
│    │  +12.5°   │         270°─┼───┼─090°            │
│    └─────┼─────┘              │ ╳ │← 045°           │
│          │                    └───┘                 │
│          ▼                     180°                 │
│                                                     │
│  PITCH: [-90 ════════╪════ +90]  +12.5°            │
│  YAW:   [  0 ════════════╪═══ 360] 045.0°          │
│                                                     │
│  [APPLY]  [RESET]                                   │
└─────────────────────────────────────────────────────┘

Behavior:
- Two sliders: pitch (-90 to +90), yaw (0 to 360)
- Visual compass rose for yaw
- Apply button sends: heading <pitch> <yaw>
- Reset returns to current ship heading
- Optional: drag on compass rose directly
```

### 4.3 System Power Toggles
**File:** `gui/components/system-toggles.js`
```
┌─ SYSTEM POWER ──────────────────────────────────────┐
│                                                     │
│  Propulsion    [●━━━━━━━○]  ON                     │
│  Sensors       [●━━━━━━━○]  ON                     │
│  Weapons       [●━━━━━━━○]  ON                     │
│  Navigation    [●━━━━━━━○]  ON                     │
│  Comms         [○━━━━━━━●]  OFF                    │
│                                                     │
└─────────────────────────────────────────────────────┘

Behavior:
- Toggle switches for each system
- Sends: (pending) system power toggles are not yet standardized in the TCP API
- Visual state matches server state
- Confirmation for critical systems (propulsion)
```

### 4.4 Target Lock Controls
**File:** `gui/components/target-controls.js`
```
┌─ TARGET LOCK ───────────────────────────────────────┐
│                                                     │
│  Selected: C001 (FRIGATE)                          │
│                                                     │
│  [ 🎯 LOCK TARGET ]    [ ✕ RELEASE ]               │
│                                                     │
│  Quick Lock: Click contact in Sensors panel        │
└─────────────────────────────────────────────────────┘

Behavior:
- Lock button sends: target <selected_contact_id>
- Release button sends: untarget
- Disabled if no contact selected
- Shows currently selected contact
- Integrates with Sensor Contacts panel selection
```

### 4.5 Weapon Fire Controls
**File:** `gui/components/weapon-controls.js`
```
┌─ FIRE CONTROL ──────────────────────────────────────┐
│                                                     │
│  [ 🚀 FIRE TORPEDO ]     Remaining: 10             │
│                                                     │
│  [ ⦿ PDC AUTO ]  ● ENABLED                         │
│                                                     │
│  [ ⛔ CEASE FIRE ]                                  │
│                                                     │
│  ⚠ No target lock — torpedoes will fire dumb      │
└─────────────────────────────────────────────────────┘

Behavior:
- Fire Torpedo: sends fire_weapon torpedo
- PDC toggle: sends fire_weapon pdc (exact “auto/cease” flags depend on server implementation)
- Warning if firing without lock
- Disabled if no ammo
```

### 4.6 Autopilot Mode Selector
**File:** `gui/components/autopilot-control.js`
```
┌─ AUTOPILOT ─────────────────────────────────────────┐
│                                                     │
│  MODE:                                              │
│  ┌──────────┬──────────┬──────────┬──────────┐     │
│  │  MANUAL  │ INTERCEPT│  MATCH   │   HOLD   │     │
│  │    ●     │          │          │          │     │
│  └──────────┴──────────┴──────────┴──────────┘     │
│                                                     │
│  Target: [ C001      ▼ ]  (dropdown of contacts)   │
│                                                     │
│  [ ENGAGE ]    [ DISENGAGE ]                        │
│                                                     │
│  Status: MANUAL CONTROL                            │
└─────────────────────────────────────────────────────┘

Behavior:
- Mode selector: manual, intercept, match, hold, hold_velocity
- Target dropdown populated from contacts
- Engage sends: autopilot <mode> [target]
- Disengage sends: autopilot off
- Shows current autopilot status/phase
```

### 4.7 Sensor Ping Button
**File:** `gui/components/sensor-ping.js`
```
┌─ ACTIVE SENSORS ────────────────────────────────────┐
│                                                     │
│  [ 📡 PING ]                                        │
│                                                     │
│  Cooldown: ████████░░ 24s                          │
│                                                     │
│  ⚠ Active ping reveals your position!              │
└─────────────────────────────────────────────────────┘

Behavior:
- Button sends: ping
- Disabled during cooldown
- Shows cooldown progress bar
- Warning about detection risk
```

### 4.8 Quick Actions Bar
**File:** `gui/components/quick-actions.js`
```
┌─────────────────────────────────────────────────────┐
│  [⛽ REFUEL] [🛑 E-STOP] [📊 STATUS] [🔄 RECONNECT]│
└─────────────────────────────────────────────────────┘

Behavior:
- Refuel: sends refuel
- E-Stop: sends emergency_stop (with confirmation)
- Status: sends status, shows in log
- Reconnect: reconnects WebSocket
```

## Phase 4 Acceptance Criteria

- [ ] Throttle slider sends thrust commands
- [ ] Heading controls send heading commands
- [ ] System toggles send power on/off commands
- [ ] Target lock button sends target command
- [ ] Weapon buttons send fire_weapon commands
- [ ] Autopilot selector sends autopilot commands
- [ ] Ping button sends ping command with cooldown
- [ ] Quick actions work (refuel, e-stop, status)
- [ ] All controls disabled appropriately (no ammo, on cooldown, etc.)
- [ ] Manual test: all controls affect server state

---

# PHASE 5: Integration & Scenarios

## Objective
Integrate all components into a cohesive layout and add scenario/mission support.

## Deliverables

### 5.1 Main Layout Grid
**File:** `gui/layouts/main-layout.js`
```
Desktop Layout (1920x1080 reference):
┌────────────────────────────────────────────────────────────────────┐
│ CONNECTION BAR                                                      │
├──────────────────┬──────────────────────────┬──────────────────────┤
│                  │                          │                      │
│   SHIP STATUS    │    NAVIGATION DISPLAY    │  SENSOR CONTACTS     │
│                  │                          │                      │
│                  │                          ├──────────────────────┤
│                  │                          │                      │
├──────────────────┤                          │    TARGETING         │
│                  │                          │                      │
│  WEAPONS STATUS  │                          │                      │
│                  ├──────────────────────────┼──────────────────────┤
│                  │                          │                      │
├──────────────────┤     EVENT LOG            │  AUTOPILOT CONTROL   │
│                  │                          │                      │
│   THROTTLE +     │                          │                      │
│   HEADING        ├──────────────────────────┼──────────────────────┤
│                  │                          │                      │
│                  │   COMMAND PROMPT         │  WEAPON/TARGET CTRL  │
│                  │                          │                      │
├──────────────────┴──────────────────────────┴──────────────────────┤
│ QUICK ACTIONS BAR                                                   │
└────────────────────────────────────────────────────────────────────┘

CSS Grid Areas:
- Responsive breakpoints at 1200px, 768px
- Panels can be collapsed
- Drag to resize (optional, Phase 6)
```

### 5.2 Scenario Loader Panel
**File:** `gui/components/scenario-loader.js`
```
┌─ SCENARIOS ─────────────────────────────────────────┐
│                                                     │
│  Available Missions:                                │
│  ┌─────────────────────────────────────────────┐   │
│  │ ⭐ Tutorial: Intercept and Approach         │   │
│  │    Learn basic navigation and autopilot     │   │
│  ├─────────────────────────────────────────────┤   │
│  │ ⭐⭐ Combat: Eliminate Threat               │   │
│  │    Destroy hostile pirate ship (5 min)      │   │
│  ├─────────────────────────────────────────────┤   │
│  │ ⭐⭐⭐ Escort: Protect the Convoy           │   │
│  │    Defend freighter from 2 fighters         │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  [ LOAD SELECTED ]   [ RESTART CURRENT ]           │
└─────────────────────────────────────────────────────┘

Data Source: get_mission or scenarios directory listing
```

### 5.3 Mission Objectives Display
**File:** `gui/components/mission-objectives.js`
```
┌─ MISSION: Escort — Protect the Convoy ──────────────┐
│                                                     │
│  OBJECTIVES                                         │
│  ☑ Locate the Canterbury                           │
│  ☑ Match velocity with convoy                      │
│  ☐ Protect freighter for 3:00          [1:45]      │
│  ☐ Optional: Stay within 10km                      │
│                                                     │
│  TIME: 01:45 / 03:00                               │
│  STATUS: IN PROGRESS                               │
│                                                     │
│  ⚠ Hostile contact detected!                       │
└─────────────────────────────────────────────────────┘

Data Source: get_mission response
Fields:
- mission_name
- objectives[] with status
- time_elapsed
- time_limit
- mission_status
```

### 5.4 State Polling / Push Manager
**File:** `gui/js/state-manager.js`
```javascript
// Specification only

class StateManager {
    /**
     * Manages simulation state synchronization.
     * 
     * Responsibilities:
     * - Poll get_state at configurable interval (default: 100ms)
     * - Poll get_events at configurable interval (default: 500ms)
     * - Distribute state updates to subscribed components
     * - Handle state diff to minimize re-renders
     * 
     * API:
     * - subscribe(component, stateKeys[]) — component notified on key changes
     * - getState(key) — synchronous access to last known state
     * - sendCommand(cmd, args) — queue command, handle response
     */
}
```

### 5.5 Recording Controls (if server supports)
**File:** `gui/components/recording-controls.js`
```
┌─ RECORDING ─────────────────────────────────────────┐
│                                                     │
│  ● REC  [ ⏹ STOP ]  Duration: 00:02:45             │
│                                                     │
│  [ ▶ START ]  [ ⏹ STOP ]  [ 💾 SAVE ]              │
└─────────────────────────────────────────────────────┘

Commands (if available):
- record_start
- record_stop
- record_save
```

## Phase 5 Acceptance Criteria

- [ ] All panels arranged in responsive grid layout
- [ ] Layout adapts to screen size
- [ ] Scenario list populated from server/files
- [ ] Scenario can be loaded
- [ ] Mission objectives display updates in real-time
- [ ] State polling works without performance issues
- [ ] Recording controls functional (if server supports)
- [ ] Manual test: complete Tutorial scenario using GUI only

---

# PHASE 6: Mobile Optimization

## Objective
Optimize for Android/mobile use with touch controls and responsive layout.

## Deliverables

### 6.1 Mobile Layout
**File:** `gui/layouts/mobile-layout.js`
```
Mobile Layout (375x812 reference — iPhone X):
┌────────────────────────────────────────┐
│ CONNECTION BAR                          │
├────────────────────────────────────────┤
│                                        │
│   [NAV] [SEN] [WPN] [LOG]  ← tabs      │
│                                        │
├────────────────────────────────────────┤
│                                        │
│                                        │
│      ACTIVE PANEL CONTENT              │
│      (swipe to change tabs)            │
│                                        │
│                                        │
├────────────────────────────────────────┤
│                                        │
│    THROTTLE          HEADING           │
│    (touch)           (joystick)        │
│                                        │
├────────────────────────────────────────┤
│ [FIRE] [LOCK] [AP] [PING]  ← actions   │
└────────────────────────────────────────┘

Features:
- Tab-based panel switching
- Swipe gestures
- Persistent controls at bottom
- Large touch targets (min 44px)
```

### 6.2 Touch Throttle Control
**File:** `gui/components/touch-throttle.js`
```
Behavior:
- Vertical swipe area
- Visual feedback on touch
- Haptic feedback if available
- Snap to 10% increments on release
- Double-tap for emergency stop
```

### 6.3 Touch Heading Control (Virtual Joystick)
**File:** `gui/components/touch-joystick.js`
```
      ┌───────────────┐
      │       ▲       │
      │               │
      │   ◄   ●   ►   │  ← drag from center
      │               │
      │       ▼       │
      └───────────────┘

Behavior:
- Circular touch area
- Drag from center to set heading
- Returns to center on release
- X axis = yaw, Y axis = pitch
- Optional: lock to cardinal directions
```

### 6.4 Gesture Handler
**File:** `gui/js/gestures.js`
```javascript
// Specification only

class GestureHandler {
    /**
     * Handles touch gestures for mobile UI.
     * 
     * Supported gestures:
     * - Swipe left/right: change tabs
     * - Long press: context menu
     * - Pinch: zoom tactical display (future)
     * - Double-tap: quick action
     */
}
```

### 6.5 Pydroid Compatibility Testing
**File:** `docs/PYDROID_TESTING.md`
```markdown
# Pydroid Testing Checklist

## Environment
- [ ] Python 3.x installed
- [ ] Flask installed (pip install flask)
- [ ] numpy, pyyaml installed

## Server Start
- [ ] Server starts without errors
- [ ] Server accepts TCP connections

## UI Start  
- [ ] UI starts without errors
- [ ] Browser loads page
- [ ] WebSocket connects

## Functionality
- [ ] All panels render
- [ ] Touch controls work
- [ ] Commands reach server
- [ ] State updates display
- [ ] Scenario can be completed
```

## Phase 6 Acceptance Criteria

- [ ] Mobile layout renders correctly on 375px width
- [ ] Touch throttle works (swipe up/down)
- [ ] Touch joystick works (drag for heading)
- [ ] Tab switching works (tap and swipe)
- [ ] All touch targets ≥ 44px
- [ ] No horizontal scroll on mobile
- [ ] Tested in Pydroid environment
- [ ] Tested on actual Android device
- [ ] Manual test: complete Tutorial scenario on mobile

---

# File Structure
```
gui/
├── index.html                 # Main entry point
├── styles/
│   ├── main.css              # CSS variables, base styles
│   ├── panels.css            # Panel component styles
│   ├── controls.css          # Control component styles
│   └── mobile.css            # Mobile-specific overrides
├── js/
│   ├── main.js               # App initialization
│   ├── ws-client.js          # WebSocket client
│   ├── state-manager.js      # State synchronization
│   ├── command-handler.js    # Command queue and dispatch
│   └── gestures.js           # Touch gesture handling
├── components/
│   ├── connection-status.js
│   ├── event-log.js
│   ├── command-prompt.js
│   ├── system-message.js
│   ├── panel.js
│   ├── ship-status.js
│   ├── navigation-display.js
│   ├── sensor-contacts.js
│   ├── targeting-display.js
│   ├── weapons-status.js
│   ├── throttle-control.js
│   ├── heading-control.js
│   ├── system-toggles.js
│   ├── target-controls.js
│   ├── weapon-controls.js
│   ├── autopilot-control.js
│   ├── sensor-ping.js
│   ├── quick-actions.js
│   ├── scenario-loader.js
│   ├── mission-objectives.js
│   ├── recording-controls.js
│   ├── touch-throttle.js
│   └── touch-joystick.js
├── layouts/
│   ├── main-layout.js        # Desktop grid layout
│   └── mobile-layout.js      # Mobile tab layout
├── ws_bridge.py              # WebSocket-TCP bridge
└── README.md                 # Setup instructions
```

---

# Command Reference (Current Server / GUI Surface)

This section is “source of truth” for the **web GUI** (`gui/`) command surface. The GUI primarily targets the TCP servers via `gui/ws_bridge.py`.

Important notes:
- `get_events` exists, but event delivery is not currently wired in the simulator, so it often returns an empty list.
- Some GUI components currently send commands/args that are not implemented by the TCP server yet (these are called out below).

| Command | Arguments | Description |
|---------|-----------|-------------|
| `get_state` | `ship` (optional) | Get state snapshot (`ship` returns detailed state) |
| `get_events` | `ship` (optional) | Get events (often empty) |
| `list_scenarios` | - | List available scenarios |
| `load_scenario` | `scenario` | Load scenario by id |
| `get_mission` | - | Get mission status |
| `get_mission_hints` | `clear` (optional) | Get mission hints |
| `pause` | `on` (optional) | Pause/unpause simulation |
| `set_thrust` | `thrust` | Scalar throttle `0.0..1.0` |
| `set_thrust_vector` | `x,y,z` | Debug-only world-frame thrust |
| `set_orientation` | `pitch,yaw,roll` | Attitude target (RCS maneuvers to reach it) |
| `set_angular_velocity` | `pitch,yaw,roll` | Angular rate target (deg/s) |
| `rotate` | `axis,amount` | Relative attitude change |
| `ping_sensors` | - | Active sensor ping |
| `lock_target` | `target_id` | Lock target contact |
| `unlock_target` | - | Unlock target |
| `autopilot` | `program` (+ `target` optional) | Engage autopilot program |
| `fire_weapon` | `weapon` (+ `target` optional) | Fire weapon (backend expects `weapon`; some GUI code uses `weapon_type`) |
| `toggle_system` | `system,state` | **Planned/WIP** (GUI uses it; server-side support not standardized yet) |

---

# Out of Scope (Do NOT Implement)

The following are explicitly OUT OF SCOPE for this GUI project:

- ❌ New gameplay features (economy, progression, etc.)
- ❌ 3D visualization / WebGL
- ❌ Sound effects / audio
- ❌ Multiplayer coordination UI
- ❌ Ship editor / loadout customization
- ❌ New scenarios (use existing 5)
- ❌ AI improvements
- ❌ Server-side changes (except bridge)
- ❌ Database / persistence
- ❌ User accounts / authentication
- ❌ Analytics / telemetry
- ❌ Localization / i18n

---

# Success Criteria (Overall)

The GUI project is COMPLETE when:

1. ✅ All 5 demo scenarios can be completed using ONLY the GUI
2. ✅ Every existing server command is accessible via GUI
3. ✅ Works on desktop browser (Chrome, Firefox)
4. ✅ Works on Android via Pydroid + mobile browser
5. ✅ No server-side changes required (except bridge)
6. ✅ Documentation updated with GUI usage instructions

---

# Appendix: ASCII Art Reference

For consistent visual language across components:
```
Status Indicators:
  ● = active/online/connected (filled circle)
  ○ = inactive/offline/disconnected (empty circle)
  ◐ = partial/connecting (half circle)
  ◉ = locked/selected (double circle)

Progress Bars:
  ████████░░░░  = 66% (filled vs empty)
  ═══════╪════  = slider position

Borders:
  ┌─────────────────┐
  │  Panel Content  │
  └─────────────────┘

Warnings:
  ⚠ = warning
  ✓ = success
  ✕ = error/close
  
Symbols:
  🎯 = target
  📡 = sensor
  🚀 = torpedo/launch
  ⛽ = fuel
  🛑 = stop
```

---

*Document Version: 1.0*
*Created for: Flaxos Spaceship Sim GUI Development*
*Scope Lock Date: [Current Date]*