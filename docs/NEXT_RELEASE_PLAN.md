# Next Release Plan - v0.6.0: Engineering + Weapons Gameplay Loops

**Release Theme**: Damage, Heat, and Sub-Targeting
**Goal**: Complete both the **Engineering** and **Weapons** gameplay loops by tying combat outcomes to subsystem damage, heat management, and targeted strikes.

---

## ✅ Release Objectives

### 1) Damage Model (Engineering + Weapons)
Introduce subsystem-level damage so combat outcomes directly affect ship functionality.

**Key deliverables**
- Subsystem health states: **online → damaged → offline → destroyed**.
- Damage propagation for **direct hits** and **AoE** weapons.
- System effects: damaged systems have degraded performance; offline systems stop working.

**Gameplay impact**
- Engineering must triage and manage system reliability.
- Tactical decisions influence which enemy capabilities are disabled.

---

### 2) Heat Management (Engineering)
Add heat generation and dissipation as a real operational constraint.

**Key deliverables**
- Heat accumulation from **reactor load**, **weapon firing**, and **sustained thrust**.
- Heat dissipation model per ship/system.
- Overheat thresholds with penalties: cooldown delays, auto-shutdown, or efficiency loss.

**Gameplay impact**
- Engineering balances power/weapon usage to avoid cascading failures.
- Tactical tradeoffs between burst damage vs sustained operations.

---

### 3) Sub-Targeting (Weapons)
Enable targeting of specific subsystems, tying directly into the damage model.

**Key deliverables**
- Command surface for selecting subsystem targets.
- Weapon effect weighting (precision vs AoE) for subsystem damage application.
- Telemetry updates to show subsystem status and critical damage.

**Gameplay impact**
- Weapons loop becomes a tactical game of disabling enemy capabilities.
- Engineering loop gains urgency through targeted damage responses.

---

## 🧭 Phased Delivery (4–6 Weeks)

### **Phase 1 — Damage Core**
- Define subsystem health schema.
- Wire damage application pipeline for hits and AoE.
- Update telemetry to expose subsystem states.

### **Phase 2 — Heat Model**
- Add heat variables per ship/system.
- Implement heat generation/dissipation rules.
- Wire overheat penalties into system performance.

### **Phase 3 — Sub-Targeting**
- Add sub-target command flow to tactical interface/commands.
- Route weapon damage to selected subsystems.
- Update telemetry and event messages for targeted hits.

### **Phase 4 — Balance & Validation**
- Tune damage/heat thresholds for gameplay pacing.
- Add regression tests for damage/heat and subsystem targeting flows.
- Update docs and scenario hints to reflect new mechanics.

---

## 🛠️ Implementation Starting Points

### Shared Foundations (Week 0–1)
- **Schema inventory**: enumerate subsystems and add health/heat fields to the core schema.
- **Telemetry shape**: define a consistent payload for subsystem status and heat metrics.
- **Command/CLI hooks**: confirm where sub-targeting and damage events surface in commands.

### Damage Model – Initial Tasks
- Add subsystem health states to system definitions.
- Create a damage application pipeline: impact → propagation → subsystem effects.
- Add initial damage hooks for direct hit and AoE weapon types.

### Heat Model – Initial Tasks
- Add per-system heat generation in the tick loop.
- Implement per-ship dissipation and overheat thresholds.
- Define penalties: output throttling, cooldown delays, and auto-shutdown rules.

### Sub-Targeting – Initial Tasks
- Add a sub-target selector to the command surface.
- Weight subsystem damage based on weapon precision and target selection.
- Update telemetry and events to report targeted hit outcomes.

### Validation – Initial Tasks
- Add regression test stubs for damage and heat calculations.
- Add a scenario checklist to ensure subsystem damage affects gameplay behavior.
---

## ✅ Acceptance Criteria

- Subsystem damage changes ship behavior in meaningful ways.
- Heat is a limiting resource that requires active management.
- Weapons can disable subsystems via sub-targeting.
- Existing weapons/sensor behaviors remain stable and deterministic.

---

## 📌 Out of Scope (Deferred)

- Drones and multi-weapon mounts (S5).
- Advanced AI doctrine (S5).
- Replay viewer and CI/CD (S6).
