# Helm UI Redesign — Unified Design Plan

**Date:** 2026-03-11
**Status:** READY FOR REVIEW
**Supersedes:** Previous GUI_REFACTOR_PLAN.md (2026-03-09)

---

## Problem Statement

14 panels in a flat grid with no grouping, duplicate functionality, and no workflow guidance. Players can't tell what controls what. Two panels (Flight Computer + Autopilot Control) both send the same `autopilot` command. Three panels have XYZ coordinate inputs. Tier switching just hides/shows panels rather than changing the feel.

---

## 1. Panel Merges (14 → 10)

| Merge | From | Into | Rationale |
|-------|------|------|-----------|
| **A** | Flight Computer + Autopilot Control + Set Course | **Flight Computer** (unified) | All three send `autopilot` or `set_course` commands. One panel for all commands. |
| **B** | Navigation Display + Delta-V Budget | **Flight Data** (new) | Both read-only flight info. No reason to separate. |
| **C** | Throttle + Heading | **Manual Flight** (new) | Both manual inputs. Throttle left, heading right. RAW tier hero. |
| **D** | Helm Requests → absorbed into Helm Queue | **Helm Queue** (expanded) | Both about queued/pending work. Requests become a sub-section. |

**Rename:** Flight Computer (Local) → **Maneuver Planner** (client-side physics calculator)

### Final Panel Inventory (10 panels)

| # | Panel | Type | Domain Color |
|---|-------|------|-------------|
| 1 | Flight Computer | Command (merged) | `--domain-nav` #3399ff |
| 2 | Contacts | Awareness | `--domain-sensor` #00ccaa |
| 3 | Flight Data | Status (merged, read-only) | `--domain-nav` #3399ff |
| 4 | Autopilot Status | Status (read-only) | `--domain-nav` #3399ff |
| 5 | Manual Flight | Manual control (merged) | `--domain-helm` #6699cc |
| 6 | RCS / Attitude | Manual control | `--domain-helm` #6699cc |
| 7 | Maneuver Planner | Expert tool (renamed) | `--domain-helm` #6699cc |
| 8 | Helm Queue | Delegation (expanded) | `--domain-comms` #9977dd |
| 9 | Docking | Special operation | `--domain-nav` #3399ff |
| 10 | (Autopilot Status listed above) | — | — |

---

## 2. Layout: 3-Column Glass Cockpit

Inspired by aviation PFD/ND/EICAS arrangement and submarine control room functional grouping:

```
+-------------------------------+-------------------------------+-------------------------------+
|  LEFT (4 cols)                |  CENTER (4 cols)              |  RIGHT (4 cols)               |
|  // SITUATIONAL AWARENESS    |  // COMMAND & CONTROL         |  // SHIP STATUS               |
|                               |                               |                               |
|  "Where am I? What's around?"|  "What do I want to do?"      |  "What is my ship doing?"     |
+-------------------------------+-------------------------------+-------------------------------+
```

Group headers styled as: `// SITUATIONAL AWARENESS` — dim, monospace, uppercase, letter-spaced, with `border-bottom: 1px solid var(--border-subtle)`. The `//` prefix evokes code comments — hard sci-fi terminal aesthetic.

Implementation: `<div class="panel-group" data-label="// FLIGHT CONTROL">` wrappers with `display: contents` (transparent to CSS grid).

---

## 3. Per-Tier Configuration

### RAW — "You ARE the flight computer" (7 panels)

**Visual Identity:**
- Accent: `#ff4444` red
- ALL monospace font
- Sharp 2px border-radius
- Subtle green scanline tint
- Numbers in raw units: m/s, m/s², N, rad

**Hero panel:** Manual Flight (8-col wide)

```
[ Contacts       ][ Flight Data      ][ Manual Flight (8-col hero)                ][ RCS       ]
                                       [ Maneuver Planner              ]
```

**Workflow strip:** `[1. PLAN] → [2. ORIENT] → [3. BURN] → [4. CHECK]`

**Disabled (not hidden):** Flight Computer shown as collapsed strip: *"AUTOPILOT AVAILABLE — switch to ARCADE or CPU-ASSIST tier"*

**Hidden:** Autopilot Status, Helm Queue, Docking

---

### ARCADE — "Point and shoot" (7 panels)

**Visual Identity:**
- Accent: `#4488ff` blue
- Mixed fonts (sans labels, mono values)
- Rounded 8px corners
- Blue glow on interactive elements
- Units: km, km/s, G-force, %

**Hero panel:** Flight Computer (6-col, center)

```
[ Contacts (6-col)              ][ Flight Computer (6-col hero)  ]
[ Flight Data    ][ Docking (when near) ][ Autopilot Status  ][ Manual Override ]
```

**Workflow strip:** `[1. DETECT] → [2. TARGET] → [3. COMMAND] → [4. MONITOR]`

**Disabled:** RCS collapsed: *"Autopilot handles attitude. Switch to RAW for manual RCS."*

**Hidden:** Heading (in Manual Override), Maneuver Planner, Helm Queue

---

### CPU-ASSIST — "Captain's chair" (6 panels)

**Visual Identity:**
- Accent: `#c0a0ff` purple
- Sans-serif throughout
- Larger fonts (1rem base)
- Bridge display feel — slightly lighter panel backgrounds
- Minimal: large touch targets, no sliders, only buttons and readouts

**Hero panel:** Autopilot Status (6-col, enlarged center display with big numbers)

```
[ Contacts (6-col)              ][ Flight Computer (6-col)       ]
[ Flight Data (6-col)           ][ Autopilot Status (6-col, BIG) ]
[ Helm Queue     ][ Docking              ]
```

**Workflow strip:** `[1. ASSESS] → [2. ORDER] → [3. QUEUE] → [4. MONITOR]`

**Hidden:** Manual Flight, RCS, Maneuver Planner (captain doesn't touch the stick)

---

## 4. Visual Design Language

### Color System

```css
/* Status (system health ONLY — never decorative) */
--status-nominal:  #00e878    /* Green = all systems go */
--status-warning:  #f0a030    /* Amber = degraded, attention */
--status-critical: #e83838    /* Red = failure, immediate */
--status-info:     #3399ff    /* Blue = autopilot active, info */
--status-offline:  #444458    /* Grey = offline, inactive */

/* Domain (functional category accents — left-border, group headers) */
--domain-nav:      #3399ff    /* Navigation, autopilot, course */
--domain-sensor:   #00ccaa    /* Sensors, contacts, detection */
--domain-weapons:  #cc4444    /* Weapons, fire control */
--domain-power:    #cc8800    /* Power, reactor, thermal */
--domain-comms:    #9977dd    /* Communications, fleet */
--domain-helm:     #6699cc    /* Helm, throttle, heading, RCS */

/* Backgrounds */
--bg-void:         #060609    /* Deep space (behind canvas) */
--bg-primary:      #0a0a0f    /* Main body */
--bg-panel:        #11111a    /* Standard panel */
--bg-panel-raised: #161622    /* Primary/interactive panel */
--bg-input:        #1a1a26    /* Form fields, inset */
--bg-hover:        #22222e    /* Hover */

/* Text */
--text-primary:    #d8d8e0    /* Main body */
--text-secondary:  #8888a0    /* Labels, section titles */
--text-dim:        #555570    /* Tertiary, disabled */
--text-bright:     #f0f0f4    /* Active headings, key values */
```

### Panel Visual Hierarchy

| Level | Background | Border | Use |
|-------|-----------|--------|-----|
| **Primary** | `#161622` raised | Bright + 3px left domain accent + drop shadow | Interactive panels (Flight Computer, Contacts) |
| **Secondary** | `#11111a` standard | Default border | Monitoring panels (Autopilot Status, Flight Data) |
| **Tertiary** | `#11111a` | Subtle border, 85% opacity | Rarely used (Helm Queue, collapsed panels) |

Implementation: `<flaxos-panel priority="primary" domain="nav">` — panel.js reads attributes, applies CSS.

### Data Display Patterns

```css
/* Dense data table (contacts, subsystems) */
.data-table-dense    { font: 0.7rem var(--font-mono); padding: 3px 8px; }

/* Key-value pair (nav readouts) */
.kv-inline           { flex row: label left (sans 0.7rem), value right (mono 0.75rem) }

/* Hero metric (closing distance, delta-V) */
.big-number          { font: 600 1.6rem var(--font-mono); tabular-nums; }

/* Status chip (ONLINE, OVERHEAT, BRAKE) */
.status-chip         { inline pill with 6px colored dot + uppercase label }
```

All mono values use `font-variant-numeric: tabular-nums` to prevent jitter on updates.

### Typography Scale

```
0.6rem   — threshold labels, keyboard shortcuts, timestamps
0.65rem  — status chips, section headers (// FLIGHT CONTROL)
0.75rem  — table data, KV pairs, most body content
0.85rem  — panel body, button labels
1.0rem   — primary panel titles
1.6rem   — hero numbers (distance, delta-V)
```

---

## 5. Workflow Guidance

### Breadcrumb Bar (below view tabs, per-view)

```
  DETECT ──▶ TRACK ──▶ LOCK ──▶ SOLUTION ──▶ FIRE
    ✓          ●                                      (● = current, ✓ = done)
```

Implementation: `<helm-workflow-strip>` component, reads `window.controlTier`, renders tier-appropriate steps. Each step clickable to scroll/highlight corresponding panel.

### Panel Badges

Small numbered circles in panel headers showing workflow order. "Next" step badge glows `--status-info` blue.

### Tutorial Integration

During tutorial: `body.tutorial-active flaxos-panel:not(.tutorial-highlight) { opacity: 0.4; }`

---

## 6. Animation Budget (Minimal)

| Trigger | Animation | Duration |
|---------|-----------|----------|
| Panel collapse/expand | Height slide + opacity | 200ms |
| Status transition (nominal→warning) | Color crossfade | 300ms |
| Alert state (critical) | Pulse glow | 1.2s loop |
| Progress bar fill | Width transition | 300ms |
| Tutorial highlight | Glow pulse | 1.5s loop |

**NOT animated:** Data value changes (use tabular-nums instead), panel reordering, scroll.

`@media (prefers-reduced-motion: reduce)` — disable all animations.

---

## 7. Responsive Breakpoints

```
>= 1440px    FULL     12-column grid, all panels per tier
1200-1439    COMPACT  Tertiary panels auto-collapse
768-1199     TABLET   6-column grid, panels full-width stack
< 768        MOBILE   Single column, existing mobile layout
```

---

## 8. Implementation Phases

### Phase 1: CSS Foundation (low risk)
- Add color/typography variables to `main.css`
- Add utility classes (`.status-chip`, `.data-table-dense`, `.kv-inline`, `.big-number`)
- Add `tabular-nums`, `prefers-reduced-motion`

### Phase 2: Panel Component Enhancement
- Add `priority` and `domain` attributes to `<flaxos-panel>` in `panel.js`
- Add `disabled-reason` attribute for tier-disabled overlay
- Reduce default padding 16px → 10px 12px

### Phase 3: Panel Merges (highest impact)
- Create `flight-data-panel.js` (nav + delta-V)
- Create `manual-flight-panel.js` (throttle + heading)
- Expand `flight-computer-panel.js` (absorb autopilot-control + set-course)
- Expand `helm-queue-panel.js` (absorb helm-requests)
- Rename `flight-computer.js` → `maneuver-planner.js`

### Phase 4: Layout Restructure
- Update `index.html`: panel-group wrappers, reduced panel count, grid areas
- Rewrite `tiers.css`: per-tier grid-template-areas, visual identity overrides
- Add workflow breadcrumb component

### Phase 5: Component Migration
- Migrate existing components to use new utility classes
- Standardize status indicators across all panels

### Phase 6: Testing
- Verify 6-7 panels per tier, all commands work, no duplicates
- Test at 1920x1080, 1366x768, 768px

---

## 9. Known Challenges

- **Shadow DOM boundary**: Tier CSS can't reach inside components. Each tier-aware component must listen for `tier-change` event internally.
- **300-line rule**: Merged Flight Computer will be large. Extract shared logic into `js/autopilot-utils.js`.
- **Engineering view**: Also needs tier reorganization — separate PR.
- **Heat system**: RCS/sensors/weapons `report_heat()` not implemented — schema values need calibration when added.
- **Flight Computer Local vs Server**: Keep both but rename Local to "Maneuver Planner" to avoid confusion. Planner = pre-calculate, Flight Computer = execute.

---

## 10. Files to Create/Modify

### New Files
- `gui/components/flight-data-panel.js` — merged nav + delta-V
- `gui/components/manual-flight-panel.js` — merged throttle + heading
- `gui/components/maneuver-planner.js` — renamed from flight-computer.js
- `gui/components/helm-workflow-strip.js` — workflow breadcrumb

### Major Modifications
- `gui/components/flight-computer-panel.js` — absorb autopilot-control + set-course
- `gui/components/helm-queue-panel.js` — absorb helm-requests
- `gui/components/panel.js` — add priority/domain/disabled-reason attributes
- `gui/styles/main.css` — new variables, utility classes
- `gui/styles/tiers.css` — complete rewrite with grid-template-areas
- `gui/index.html` — restructure helm view

### Deprecated (remove from helm view, keep files for other views)
- `gui/components/autopilot-control.js` — absorbed into flight-computer-panel
- `gui/components/set-course-control.js` — absorbed into flight-computer-panel
- `gui/components/helm-requests.js` — absorbed into helm-queue-panel

---

*End of plan. Ready for review and implementation.*
