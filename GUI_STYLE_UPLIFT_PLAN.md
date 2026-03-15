# GUI Style & Vibe Uplift Plan

**Target:** Flaxos Spaceship Sim — `gui/` directory
**Goal:** Transform a functional prototype into a polished hard sci-fi bridge simulator
**Reference aesthetic:** The Expanse, not Star Trek. Utilitarian. Earned grime. No chrome.

---

## Current State Assessment

The GUI has solid bones: a working design system (`main.css`), per-tier visual identity (`tiers.css`), Shadow DOM components, a 12-column grid view layout, and an established color vocabulary. What it lacks is *atmosphere*. The panels read as developer UI. The typography is flat. The canvas (tactical map) has no depth. The data displays have no weight.

**Existing strengths to preserve:**
- CSS custom property architecture (`--bg-panel`, `--status-nominal`, etc.) — this is the right foundation
- Domain color system (`--domain-nav`, `--domain-weapons`, etc.) — extend, don't replace
- Tier system (raw/arcade/cpu-assist) with body class switching — keep exactly as-is
- `flaxos-panel` Shadow DOM structure — uplift the internals, not the API
- JetBrains Mono + Inter font pairing — already correct choices

**Problems to fix:**
- Panel headers read as generic web UI (flat `rgba(255,255,255,0.02)` background, no domain personality)
- Primary panels (`priority="primary"`) have a domain-colored left border but no other visual differentiation
- Background `#12121a` is indistinguishable from `#0a0a0f` in practice — contrast is too low
- Status indicators (dots) are tiny and don't communicate urgency
- The tactical map canvas background `#0d0d12` looks identical to every other panel
- No animations on live data (velocity, sensor updates, weapon status)
- Buttons are generic `--bg-input` blocks with no personality
- No scanline/noise texture — the "void of space" feeling is absent
- Status bars and headers are not visually dominant enough to read at a glance

---

## Section 1: Visual Identity & Design Language

### Color Palette

Extend the existing CSS custom properties — do not replace them. Add new tokens alongside.

```css
:root {
  /* === EXISTING (do not change) === */
  --bg-primary:      #0a0a0f;
  --bg-panel:        #12121a;
  --bg-panel-raised: #161622;
  --bg-input:        #1a1a24;
  --bg-hover:        #22222e;
  --border-default:  #2a2a3a;
  --border-active:   #3a3a4a;
  --text-primary:    #e0e0e0;
  --text-secondary:  #888899;
  --text-dim:        #555566;
  --status-nominal:  #00ff88;
  --status-warning:  #ffaa00;
  --status-critical: #ff4444;
  --status-info:     #00aaff;

  /* === NEW: Deeper void backgrounds === */
  --bg-void:         #050508;   /* space between panels */
  --bg-panel-deep:   #0d0d14;   /* canvas surfaces, map backgrounds */
  --bg-glass:        rgba(22, 22, 34, 0.85); /* frosted panel headers */

  /* === NEW: Glow values (for box-shadow use) === */
  --glow-nominal:    0 0 8px rgba(0, 255, 136, 0.35);
  --glow-warning:    0 0 8px rgba(255, 170, 0, 0.35);
  --glow-critical:   0 0 12px rgba(255, 68, 68, 0.5);
  --glow-info:       0 0 8px rgba(0, 170, 255, 0.3);
  --glow-tier:       0 0 10px rgba(var(--tier-accent-rgb), 0.25);

  /* === NEW: Tier accent RGB triplets (for rgba() use) === */
  /* Set alongside --tier-accent in tiers.css */
  /* body.tier-raw        { --tier-accent-rgb: 255, 68, 68; } */
  /* body.tier-arcade     { --tier-accent-rgb: 68, 136, 255; } */
  /* body.tier-cpu-assist { --tier-accent-rgb: 192, 160, 255; } */

  /* === NEW: Noise/texture overlay opacity === */
  --noise-opacity:   0.018;   /* body::before pseudo-element */
  --scanline-opacity: 0.012;  /* body::after in tier-raw */

  /* === NEW: Alert level colors === */
  --alert-advisory:  #4488ff;  /* blue — informational */
  --alert-caution:   #ffaa00;  /* amber — attention required */
  --alert-warning:   #ff6600;  /* orange — action required */
  --alert-critical:  #ff2222;  /* red, saturated — immediate */
}
```

### Space Background Texture

The void between panels should feel like the hull interior of a working ship: dark, slightly textured, not pristine.

Add a subtle SVG noise pattern to `body` via a `::before` pseudo-element in `main.css`:

```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: -1;
  /* Fine grain noise — generate as a data URI from an SVG feTurbulence filter */
  background-image: url("data:image/svg+xml,...");
  opacity: var(--noise-opacity, 0.018);
}
```

The actual SVG noise data URI should use `feTurbulence` with `baseFrequency="0.65"` and `stitchTiles="stitch"`. This adds imperceptible grain that prevents the flatness of solid fills. Do not make it visible — test at 0.015–0.02 opacity.

Set `--bg-void` as the body `background-color` rather than `--bg-primary`. This makes the gap between panels read as genuine depth.

### Tier-Specific Personality (Extend Existing Rules)

**RAW tier — "You ARE the flight computer"**
- Accent: `#ff4444` (red)
- Body class: `.tier-raw`
- Personality: Terminal green-on-black ghost under red accents. Phosphor feel.
- Add: `body.tier-raw` gets a very faint green tint on `--text-primary` (shift to `#d8e8d8`)
- Add: scanline overlay is already present (`tiers.css` line 55–68) — keep it, increase opacity slightly to `0.022`
- Add: `flaxos-panel` in tier-raw: `border-radius: 0` (not 2px, truly sharp)
- Add: panel headers in tier-raw use `font-family: var(--font-mono)` for the title text

**ARCADE tier — "Point and shoot"**
- Accent: `#4488ff` (blue)
- Body class: `.tier-arcade`
- Personality: Clean, confidence-inspiring. Slightly elevated brightness.
- Add: `body.tier-arcade` background shift to `#0c0c16` (bluer dark)
- Add: primary panels get a faint blue `box-shadow: inset 0 0 30px rgba(68,136,255,0.03)`
- Buttons in arcade: subtle blue glow on hover already works, expand to `0 0 8px rgba(68,136,255,0.5)` on :hover

**CPU-ASSIST tier — "Captain's chair"**
- Accent: `#c0a0ff` (purple)
- Body class: `.tier-cpu-assist`
- Personality: Elevated, command-level. Calmer. More breathing room.
- Add: `body.tier-cpu-assist` panel font-size `0.95rem` (already at 1rem — keep)
- Add: primary panels get `border-top: 2px solid rgba(192,160,255,0.4)` instead of left border
- Add: panel header text gets `letter-spacing: 0.08em` for gravitas

---

## Section 2: Panel-by-Panel Uplift

### Panel Container (`gui/components/panel.js`)

This is the highest-leverage change. Every panel in the UI inherits from here.

**Panel header redesign:**

Current header background is `rgba(255,255,255,0.02)` — nearly invisible. Replace with:

```css
.header {
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.035) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
  border-bottom: 1px solid var(--border-default, #2a2a3a);
  /* Add a 1px top highlight — simulates edge lighting */
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}
```

**Title text:**

Current: `color: var(--text-secondary)` — too quiet. Headers should identify panels at a glance.

```css
.title {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-secondary, #888899);
  /* Add domain color accent on the title when domain is set */
}

/* When a domain is set, tint the title */
:host([domain]) .title {
  color: color-mix(in srgb, var(--panel-domain-color) 40%, var(--text-secondary));
}
```

**Primary panel distinction:**

```css
:host([priority="primary"]) {
  background: var(--bg-panel-raised, #161622);
  border-color: var(--border-active, #3a3a4a);
  border-left: 3px solid var(--panel-domain-color, var(--border-active));
  box-shadow:
    0 2px 12px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
```

**Domain-colored header accent line:**

Add a 2px colored line at the very top of each panel header (above the `padding`) using `::before` on `.header`:

```css
.header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--panel-domain-color, transparent);
  opacity: 0.6;
}
.header { position: relative; }
```

This gives each panel a thin colored eyebrow that identifies its functional domain at a glance — much like MFD bezels on military aircraft.

**Disabled state:**

Current disabled overlay is `rgba(6,6,9,0.6)` — fine. Add a subtle texture to the overlay to sell "dead panel":

```css
.disabled-overlay {
  background:
    repeating-linear-gradient(
      -45deg,
      transparent,
      transparent 3px,
      rgba(0, 0, 0, 0.08) 3px,
      rgba(0, 0, 0, 0.08) 4px
    ),
    rgba(6, 6, 9, 0.65);
}
```

### Navigation Display Panels

Target feel: JTAC/MFD navigation page. Heading/bearing readouts should look like instruments, not text.

- Large numeric readouts for heading (bearing): use `.big-number` class from `main.css` — already defined, apply it
- Heading: show as `XXX°` with zero-padding to 3 digits, always
- Speed: `X.XXX km/s` with fixed decimal width using `font-variant-numeric: tabular-nums`
- Altitude/Z-position: if near zero, dim it (ship is coplanar)
- Add a thin horizontal separator between navigation groups (position vs velocity vs fuel)
- Range rings concept for distance-to-target: a small arc widget, not just a number

### Sensor Contacts Panel (`gui/components/sensor-contacts.js`)

Target feel: ESM/sonar contact list on a submarine — sparse, clinical, organized.

Current table: 5 columns (ID, CLASS, BRG, RANGE, CLOSURE). This is correct. Uplift:

- Contact ID column: use amber (`#ffaa00`) for unknowns, green for friendlies, red for hostiles — already partially implemented via CSS classes, make it consistent
- Add a very thin 1px left-border color strip on each row matching the contact IFF color
- Stale contacts: current `opacity: 0.35` is correct — add a slow blink (`animation: stale-blink 2s ease-in-out infinite`) at `0.2–0.4` opacity range
- Empty state: replace emoji circle `○` with an ASCII radar sweep animation — a rotating `\` character cycling through `| / - \` at 500ms intervals using CSS `animation`
- Active ping: when a ping fires, flash the entire panel border briefly with `--status-info` color using a CSS keyframe on the `:host` element — 200ms flash, 400ms fade

```css
@keyframes ping-flash {
  0%   { border-color: var(--status-info, #00aaff); box-shadow: var(--glow-info); }
  100% { border-color: var(--border-default, #2a2a3a); box-shadow: none; }
}
:host(.pinging) {
  animation: ping-flash 0.6s ease-out;
}
```

Add the `.pinging` class in JS when the ping button is fired, remove it after 700ms.

### Weapons Status Panel (`gui/components/weapons-status.js`)

Target feel: Reload indicator on a naval gun control display. Mechanical, state-driven.

- Weapon sections: add a header bar that uses `--domain-weapons: #cc4444` as the left-border accent
- `READY` status badge: currently `rgba(0,255,136,0.2)` background. Make it a solid `1px` border instead with a glowing dot: `border: 1px solid var(--status-nominal); box-shadow: 0 0 6px rgba(0,255,136,0.4)`
- `RELOADING` state: replace the simple pulse with a fill-bar animation — show reload progress as a horizontal bar that fills from left to right over the reload duration
- `EMPTY` state: add a `--status-critical` flicker (irregular, not smooth pulse) — use CSS `steps()` timing:

```css
@keyframes ammo-empty {
  0%, 89%, 91%, 100% { opacity: 1; }
  90%                 { opacity: 0.3; }
}
.weapon-status.empty { animation: ammo-empty 1.8s steps(1) infinite; }
```

- Ammo count: display as `XXX / XXX` with the current count in a larger font than the max
- Add a thin ammo-remaining bar beneath the count — full=green, 50%=amber, 25%=red, 0%=flicker

### Targeting & Firing Solution Panel

Target feel: Fighter jet HUD symbology — angular brackets, confidence as a fill level.

- Lock state readout: `UNLOCKED` (dim), `TRACKING` (amber pulse), `LOCKED` (green steady)
- Firing solution confidence: don't just show a percentage. Show a graphical "probability cone" indicator — a simple SVG arc that sweeps from 0 to the confidence angle, with color transitioning from red at 0% to green at 80%+
- Time-to-intercept: large monospace countdown, red when under 10s
- Locked target name: display in tier-accent color, not plain white

### Subsystem Status Panel (`gui/components/subsystem-status.js`)

Target feel: Damage control board on a naval vessel. Schematic, not decorative.

- Each subsystem row: expand to show a mini health bar, not just text status
- Health bar color: smooth gradient from `#00ff88` (100%) → `#ffaa00` (50%) → `#ff4444` (25%) → `#ff2222` with flicker (0%)
- Destroyed state: add a diagonal hatch pattern over the bar using CSS `repeating-linear-gradient`
- Cascade damage: when a subsystem has cascading effects, add a small `[CASCADE]` label in `--status-critical` color
- Mission-kill indicator: when drive is destroyed (mission over), add a full-row red flash

### Engineering / Power Gauges

Target feel: Power plant control room — analog-feeling digital readouts.

- Power distribution: show as a vertical bar chart for each subsystem, not a list of numbers
- Thermal display: the heat bar should have a gradient fill — cool blue at low heat → amber at 70% → red at 90% — with a "danger zone" shading on the bar above the threshold line
- Reactor output: large centered number with unit label. If at max output, add a faint amber border pulse on the reactor section
- Radiators: show deployed/retracted state as a simple schematic (two lines extending from a central node — draw with CSS border tricks, no image needed)

### Combat Log (`gui/components/combat-log.js`)

Target feel: Ballistic engagement record — sparse, timestamped, causal.

- Each entry: left border color coded by event type (hit=green, miss=amber, system damage=red, kill=red+bright)
- Timestamps: `HH:MM:SS.s` format in `--text-dim`, never larger than 0.65rem
- New entries: slide in from the bottom with a 150ms ease-out translate + opacity transition
- Important events (system destroyed, ammo depleted): bold, full-width highlight row

---

## Section 3: Status & Alert System

### Alert Hierarchy

Four alert levels, each with distinct visual treatment:

| Level | Color | CSS Variable | Visual Behavior |
|-------|-------|-------------|-----------------|
| Advisory | `#4488ff` | `--alert-advisory` | Static blue indicator, no animation |
| Caution | `#ffaa00` | `--alert-caution` | Slow amber pulse, 2s period |
| Warning | `#ff6600` | `--alert-warning` | Faster orange pulse, 1s period |
| Critical | `#ff2222` | `--alert-critical` | Rapid red flash, 0.4s period, irregular |

Implement as a body-level class system: `body.alert-advisory`, `body.alert-warning`, etc. The status bar and tier accent line both react to the highest active alert level.

### System Health Color Gradient

Replace the binary green/yellow/red threshold system with a continuous gradient approach:

```css
/* Use color-mix or a JS-computed inline style */
/* Health: 100% = #00ff88, 50% = #ffaa00, 25% = #ff4444, 0% = #ff2222 + flicker */

function healthColor(pct) {
  if (pct > 0.75) return `color-mix(in srgb, #00ff88 ${(pct-0.75)*400}%, #ffaa00)`;
  if (pct > 0.25) return `color-mix(in srgb, #ffaa00 ${(pct-0.25)*200}%, #ff4444)`;
  return '#ff4444';  /* + apply CSS flicker class below 15% */
}
```

### Damage State Visualization

When a subsystem drops below 25% health, its panel and readouts should degrade visually:

- **Signal degradation:** Apply a subtle `filter: contrast(0.9) brightness(0.95)` to the affected panel
- **Flicker:** Use a CSS animation that briefly cuts `opacity` to 0.7 and back, irregularly timed using multiple `animation-delay` values on different elements
- **Static noise:** For destroyed sensors specifically, apply a CSS `background-image: url(noise-data-uri)` with high opacity to the sensor contacts list to simulate interference
- **Cascade indicators:** A red `!` badge on the affected panel's title area

```css
/* Damaged panel — apply via JS by setting data-health attribute */
:host([data-health="impaired"]) .content {
  animation: damage-flicker 4s ease-in-out infinite;
}
:host([data-health="critical"]) .content {
  animation: damage-flicker 1.5s ease-in-out infinite;
  filter: contrast(0.85) brightness(0.9);
}

@keyframes damage-flicker {
  0%, 94%, 96%, 98%, 100% { opacity: 1; }
  95%, 97%                 { opacity: 0.65; }
}
```

### Toast / System Message Uplift

Current `system-message` component slides in from the right correctly. Uplift:

- Add a left-border 3px solid matching the message type color
- Add a faint glow on the border: `box-shadow: -2px 0 8px rgba(color, 0.4)`
- Critical messages: add a `background: rgba(255,34,34,0.08)` tint
- Auto-dismiss: add a thin progress bar along the bottom of the toast that drains over the dismiss timeout

---

## Section 4: Typography & Data Presentation

### Numeric Readout Standards

All numeric data that changes in real-time must use:
- `font-family: var(--font-mono)` — JetBrains Mono
- `font-variant-numeric: tabular-nums` — prevents layout shift as digits change
- `letter-spacing: 0` or `-0.02em` — tighter than default for instrument feel

**Fixed-width formatting rules:**
- Heading/bearing: always 3 digits, zero-padded — `007°` not `7°`
- Speed: always show 2 decimal places for m/s values under 100 m/s — `042.30 m/s`
- Range: `km` for ≥1000m, `m` for <1000m — never mix units in the same readout
- Percentages: always 3 characters — ` 87%` (space-padded) or `100%`
- Negative values: always show sign — `−042.3` using the minus sign (`−`, U+2212), not hyphen

**Hero number sizing:**

The `.big-number` class in `main.css` is already at `1.6rem`. Use it on:
- Primary heading display in nav panels
- Speed readout in flight data
- Distance to target in targeting
- Current power output in engineering

Add a `.metric-number` variant at `1.1rem` for secondary but still prominent values.

### Label Conventions

- Section headers within panels: `font-size: 0.65rem`, `text-transform: uppercase`, `letter-spacing: 0.12em`, `color: var(--text-dim)` — already in use in some components, standardize everywhere
- Data labels (key in key-value pairs): `font-family: var(--font-sans)`, `color: var(--text-secondary)` — use Inter for labels, mono for values. This contrast is important and should be consistent across all components.
- Unit labels: always smaller than the value, always `var(--text-dim)` — `12.4 <span class="unit">km/s</span>`

### Value Color Coding

Establish and enforce these rules everywhere:

| Condition | Color Variable | When to use |
|-----------|---------------|-------------|
| Nominal / in range | `--status-nominal` `#00ff88` | Systems healthy, readings expected |
| Caution threshold | `--status-warning` `#ffaa00` | Approaching limit, attention needed |
| Critical / limit | `--status-critical` `#ff4444` | At or past limit, action required |
| Informational | `--status-info` `#00aaff` | Target data, selected items, advisory |
| Offline / unknown | `--text-dim` `#555566` | No data, system offline, stale |
| Active / live | `--text-primary` `#e0e0e0` | Default live data |

**Enforce via JS:** Components should set color with a helper function:

```js
function valueColorClass(value, { nominal, caution, critical }) {
  if (value <= critical) return 'text-critical';
  if (value <= caution)  return 'text-warning';
  if (value <= nominal)  return 'text-nominal';
  return '';  // default text-primary
}
```

---

## Section 5: Tactical Map Overhaul

The tactical map canvas is the most visually distinct element in the GUI. Currently it renders cleanly but without atmosphere. Target: a passive sensor display on a hard-science warship.

### Background & Grid

Replace solid `#0d0d12` fill with a multi-layer background:

```js
// In _draw(), replace the single fillRect with:
ctx.fillStyle = '#050508';       // deep void
ctx.fillRect(0, 0, w, h);

// Vignette: darker at edges, slightly lighter at center
const vignette = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w,h)*0.7);
vignette.addColorStop(0, 'rgba(20, 20, 30, 0.15)');
vignette.addColorStop(1, 'rgba(0, 0, 0, 0.6)');
ctx.fillStyle = vignette;
ctx.fillRect(0, 0, w, h);
```

Grid lines: current `rgba(40,40,60,0.5)` — reduce to `rgba(30,30,50,0.4)`. The grid should be a ghost, not a feature.

### Range Rings

Current range rings at 25/50/75/100% are functional. Uplift:

- Only draw at 50% and 100% — 4 rings is cluttered
- At 100% range ring: draw with a slightly heavier `lineWidth: 1.5` and a label
- Add a second, visually distinct ring for **sensor range** (pull from ship state) in teal `rgba(0,200,160,0.25)` with a label "SENSOR RANGE"
- Range ring labels: position them at the `30°` mark (not `0°` — the right edge) so they don't conflict with contacts

### Contact Rendering

Current contacts: simple filled circle, 5px radius, faction color. Upgrade to IFF-specific iconography drawn in canvas:

| IFF | Icon | Description |
|-----|------|-------------|
| Player | Filled triangle (pointing heading direction) | Already implemented — keep |
| Friendly | Diamond (square rotated 45°) | 8px, stroke only, fill at 30% opacity |
| Hostile | Square | 8px, stroke 1.5px, fill at 20% opacity, slightly larger at 10px |
| Unknown | Circle with `?` in center | 8px radius, stroke dashed |
| Neutral | Circle | 6px, thin stroke, muted color |

Contact label format (existing logic is correct, uplift the text style):
- Name: `font: '10px "JetBrains Mono", monospace'` — keep
- Classification in parentheses: dim it with `globalAlpha: 0.6`
- Detection method badge: small prefix in brackets — already `[P]`, `[A]`, `[V]`
- Add: bearing label below the contact in `0.5` opacity — `BRG 247°` in 9px mono

### Targeting Brackets

Current implementation draws corner brackets (L-shapes at 4 corners of a 12px box). This is correct. Uplift:

- Locked state: brackets are solid, color `#ffffff`, with a slow rotation animation (`transform: rotate(45deg)` over 4s — the brackets slowly spin around the contact, indicating active track)
- Acquiring state: brackets are dashed, `#ffaa00`, and slightly larger (16px box)
- Add a closing animation when lock is achieved: brackets start at 20px and animate to 12px over 0.3s

Implement the lock animation via a `_lockAnimStart` timestamp: subtract elapsed time from bracket size, clamped to minimum.

### Firing Solution Confidence Cones

Current implementation draws filled triangles from player to target. Uplift:

- Fill: gradient from opaque at player end to transparent at target end — more realistic (uncertainty grows with range)
- Edge lines: draw the two sides of the cone as dashed lines, not just the filled area
- Low confidence (<40%): fill becomes hatched lines instead of solid, indicating unreliable solution
- Label at midpoint of cone, not near player: position at 40% along the cone length

### Projectile Tracks

Current: a dot with a velocity trail. Uplift:

- Railgun rounds: bright `#ffaa00` dot with a longer trail (trail length = `velMag * 3` instead of `0.5`), trail fades from `rgba(255,170,0,0.8)` to `rgba(255,170,0,0)` over 30px
- PDC rounds: smaller red dots (`rgba(255,100,100,0.9)`), very short trail (5px), many simultaneous
- Torpedoes: larger dot (4px), amber color, with an approach vector arc drawn ahead of it (predicted path for next 10 seconds)
- On impact: spawn a brief radial burst — 4–6 short lines at random angles, 300ms duration, fading from `rgba(255,200,100,1)` to transparent

### Scale Display & Controls

The control bar buttons (V, H, G, W, T, S) are currently generic. Uplift:

- Active state: instead of `background: var(--status-info)`, use `border-color: var(--tier-accent); box-shadow: 0 0 6px rgba(tier-accent, 0.4)`
- Button labels: spell them out in a tooltip (title attribute) but also add a 2-char minimum display — current single letters work but add a small label below each group of buttons

### Compass Rose

Current compass is functional but small (30px radius). Expand to 40px, add:
- Tick marks at 45° intervals (not just NSEW labels)
- Faint heading line from center to N that rotates with ship heading
- N label in tier-accent color to distinguish from dimmer NSEW

---

## Section 6: Sound Design Hooks (CSS Animation Triggers)

Sound will be implemented separately, but the CSS must fire the right hooks for a JS audio layer to observe. Use `animationstart` and class addition/removal as the trigger mechanism.

### Event → CSS Class → Sound Hook

| UI Event | CSS Class to Add | Suggested Audio |
|----------|-----------------|-----------------|
| Active sensor ping fired | `.pinging` on `sensor-contacts` host | Sonar-style echo ping, 600ms |
| Target locked | `.lock-acquired` on `targeting-display` host | Two-tone lock tone |
| Target lost | `.lock-lost` on `targeting-display` host | Low beep sequence |
| Weapon fired | `.weapon-fired` on `weapon-controls` host | Low frequency thump (in vacuum, structural) |
| Weapon empty (ammo 0) | `.ammo-depleted` on panel | Dry click + warning tone |
| System damage received | `.damage-event` on `subsystem-status` host | Hull impact |
| System destroyed | `.system-destroyed` on panel | Deep structural creak + alarm |
| Critical alert | `body.alert-critical` | Klaxon, short burst |
| Advisory alert | `body.alert-advisory` | Soft chime, once |
| Mission complete | `body.mission-success` | Completion chord |
| Mission failed | `body.mission-failed` | Low warning sequence |

### Alert Tone Hierarchy

```
Advisory  →  Single soft beep (440Hz, 80ms, low volume)
Caution   →  Double beep (520Hz, 80ms + 80ms gap + 80ms, medium)
Warning   →  Triple beep, higher pitch (660Hz, faster cadence)
Critical  →  Klaxon — alternating 880Hz/440Hz, repeating until acknowledged
```

The CSS classes above serve as sound hooks. A JS audio manager should observe `document.body.classList` and `MutationObserver` to trigger sounds on class changes. The audio layer does not exist yet — this plan documents the CSS contracts it can rely on.

---

## Section 7: Responsive Considerations

### Breakpoints

The current breakpoints are:
- `>1200px`: 12-column grid (full layout)
- `768–1200px`: 6-column grid (panels stack to full width)
- `<768px`: 1-column grid (mobile stacking)

These are correct. Add a new breakpoint for 1366px (laptop/720p displays):

```css
@media (max-width: 1440px) and (min-width: 1201px) {
  /* Reduce panel font sizes slightly */
  :root {
    --font-size-xs: 0.65rem;
    --font-size-sm: 0.75rem;
    --font-size-base: 0.85rem;
  }
  /* Compress panel headers */
  /* .header { min-height: 30px; padding: 6px 12px; } */
  /* (Apply inside Shadow DOM via part() or CSS custom property) */
}
```

### Panel Priority at Smaller Sizes

At `<1440px`, tertiary panels (`priority="tertiary"`) should auto-collapse (set `collapsed` attribute via JS when viewport is below threshold). Secondary panels should still render but may reduce their `min-height`.

```js
// In a resize observer or layout manager:
const isSmallViewport = window.innerWidth < 1440;
document.querySelectorAll('flaxos-panel[priority="tertiary"]').forEach(p => {
  p.collapsed = isSmallViewport;
});
```

At `<1200px` (6-column):
- Tactical map: must stay full width (`grid-column: span 6`) — it loses meaning at half size
- Navigation display: reduce decimal precision in readouts (1 decimal vs 2)

At `<768px` (mobile):
- Show only the single most important panel for the active station
- Hide all secondary and tertiary panels
- The tier system does not apply — show CPU-ASSIST behavior on mobile regardless

### Panel min-height at Breakpoints

The current `clamp()` values on `--panel-height-sm/md/lg` in `index.html` are good. Add one more level:

```css
:root {
  --panel-height-xs: clamp(120px, 16vh, 200px);  /* for controls-only panels */
}
```

Use `--panel-height-xs` for the bridge controls bar and workflow strip panels.

---

## Section 8: Implementation Approach

### Phase 1 — Quick Wins (CSS-only, no JS changes) — ~1 day

These changes require only edits to `main.css` and `tiers.css` and produce immediate visible impact:

1. **`main.css`:** Change `body` background-color to `--bg-void: #050508`
2. **`main.css`:** Add noise texture pseudo-element to `body::before`
3. **`main.css`:** Add `--tier-accent-rgb` triplets to `tiers.css` body class rules
4. **`main.css`:** Upgrade `.big-number`, `.status-chip`, `.kv-inline` padding and spacing — make them breathe more
5. **`tiers.css`:** Set `border-radius: 0` for tier-raw (currently 2px)
6. **`tiers.css`:** Add `box-shadow: inset 0 0 30px rgba(68,136,255,0.03)` to tier-arcade primary panels
7. **`index.html` inline styles:** Panel group `data-label` headers — increase `letter-spacing` to `0.15em`

### Phase 2 — Panel Container Uplift (`panel.js`) — ~0.5 day

1. Add domain-colored eyebrow line on `.header::before`
2. Upgrade header gradient (replace `rgba(255,255,255,0.02)` with proper gradient)
3. Upgrade `.title` to pick up domain color tint
4. Add `box-shadow: inset 0 1px 0 rgba(255,255,255,0.05)` to header
5. Add diagonal hatch texture to disabled overlay
6. Add `data-health` attribute observation for damage flicker CSS class application

### Phase 3 — Component-by-Component Uplift — ~2–3 days

Work through components in priority order:

1. `sensor-contacts.js` — ping flash, stale contact blink, IFF row color strips
2. `weapons-status.js` — reload bar animation, ammo fill bar, empty state flicker
3. `targeting-display.js` — lock bracket animation, confidence arc SVG
4. `subsystem-status.js` — health gradient bars, cascade badges, destroy flicker
5. `combat-log.js` — slide-in animation, colored left borders
6. `status-bar.js` — alert level integration, tier-accent border
7. `thermal-display.js` — heat gradient, danger zone marker

### Phase 4 — Tactical Map — ~1 day

1. Multi-layer background with vignette
2. IFF-specific contact icons (diamond, square, dashed circle)
3. Refined projectile trails and impact burst
4. Targeting bracket lock animation
5. Firing solution cone gradient and hatch for low confidence
6. Compass rose upgrade

### Phase 5 — Sound Hook CSS Classes — ~0.5 day

1. Define all CSS class contracts listed in Section 6
2. Add the classes in the right JS locations (component event handlers)
3. Document the class API in a comment block in `main.css`

### CSS Custom Property Injection into Shadow DOM

Shadow DOM components cannot inherit most CSS custom properties from the light DOM unless they are explicitly inherited. The current components use `var(--font-mono)` etc. — this works because custom properties **do** inherit through Shadow DOM by default (they pierce the boundary).

However, `body::before` noise texture and `body.tier-raw` font-family rules do **not** affect Shadow DOM internals. Each component's Shadow DOM `<style>` block must:

1. Declare its own `font-family` using `var(--font-mono)` — already done in most components
2. Use CSS custom properties (which inherit) rather than hardcoded colors — already mostly done
3. For tier-specific behavior inside Shadow DOM: rely on custom property changes driven by `tiers.css` rules on `body` — this works correctly

**Do not** attempt to inject `@import` or `link` tags into Shadow DOM. Use CSS custom property values exclusively for cross-boundary theming.

### Animation Performance Considerations

The following animations must use GPU-compositable properties only (`transform`, `opacity`):

- Contact slide-in in combat log: `translateY(8px) → translateY(0)` + `opacity`
- Lock bracket scale animation: `scale(1.5) → scale(1)` + position via `transform: translate()`
- Panel ping flash: `opacity` only, or `box-shadow` (not composited but acceptable for rare events)
- Status dot pulse: `opacity` — already correct in `main.css`

Do **not** animate:
- `background-color` in loops (forces repaint every frame)
- `border-color` in loops (same issue)
- `width` or `height` of non-absolute elements in loops (causes layout reflow)

Use `will-change: opacity` on elements that animate continuously (status dots, damage flicker). Remove `will-change` from elements that animate rarely.

The tactical map `_draw()` is already on Canvas 2D — it bypasses the CSS paint pipeline entirely. No CSS animation concerns apply there.

### Reduced Motion Compliance

`tiers.css` already has a `@media (prefers-reduced-motion: reduce)` block. Extend it:

```css
@media (prefers-reduced-motion: reduce) {
  /* Disable all new animations added by this uplift */
  .contact-row { transition: none; }
  :host(.pinging) { animation: none; box-shadow: 0 0 4px var(--status-info); }
  :host([data-health="impaired"]) .content { animation: none; filter: brightness(0.92); }
  /* Tactical map: disable bracket rotation, use static display */
}
```

---

## Appendix: File Edit Checklist

When implementing this plan, the following files require changes. Read each file fully before editing.

| File | Changes |
|------|---------|
| `gui/styles/main.css` | Noise texture on `body::before`, new CSS custom properties, `.metric-number` class, phase 1 quick wins |
| `gui/styles/tiers.css` | `--tier-accent-rgb` triplets, `border-radius: 0` for raw, arcade inset shadow, reduced-motion additions |
| `gui/components/panel.js` | Header gradient, eyebrow line, title domain tint, disabled hatch texture, `data-health` attribute support |
| `gui/components/tactical-map.js` | Vignette, IFF icons, projectile trails, bracket animation, solution cone gradient, compass rose |
| `gui/components/sensor-contacts.js` | Ping flash class, stale blink, IFF row strips, empty state radar sweep |
| `gui/components/weapons-status.js` | Reload bar, ammo fill bar, empty flicker, status badge as border+glow |
| `gui/components/subsystem-status.js` | Health gradient bars, cascade badges, destroy flicker, `data-health` on host |
| `gui/components/combat-log.js` | Slide-in animation, left border color coding |
| `gui/index.html` | Panel group label spacing only — no structural changes |

**Do not change:**
- The tier system structure in `tiers.css` — only extend it
- The `flaxos-panel` public API (attributes, events)
- The `wsClient` or `stateManager` APIs
- Any Python server files
- The view grid layout (12-column, panel class names)

---

*This plan documents what to build, not why it will look good. The "why" is: space is dark, ships are working machines, and every pixel of light on this bridge was paid for by the reactor.*
