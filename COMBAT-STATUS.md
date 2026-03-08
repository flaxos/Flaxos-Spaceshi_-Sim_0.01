# Combat System Status

## What Works

- **Railgun (UNE-440):** Physics-based firing solutions with lead prediction, 20 km/s muzzle velocity, 500 km effective range, 5s cycle time, 20-round magazine
- **PDC (Narwhal-III):** Auto-turret point defense, 3 km/s muzzle velocity, 5 km effective range, 0.1s cycle time, 2000-round magazine
- **Firing Solutions:** Quadratic intercept calculation with lead angle, time-of-flight, hit probability, and confidence scores
- **Targeting Pipeline:** Full state machine: NONE -> TRACKING -> ACQUIRING -> LOCKED -> (LOST -> TRACKING)
- **Track Quality:** Degrades with range (linear to 0.2 at max lock range) and target acceleration (10G+ causes degradation); sensor damage compounds both
- **Confidence Scores:** Firing solutions include 0-1 confidence combining track quality, range accuracy, and lateral velocity
- **Subsystem Damage:** Five subsystems (propulsion, RCS, sensors, weapons, power) with ONLINE -> DAMAGED -> OFFLINE -> DESTROYED progression
- **Mission Kill Detection:** Mobility kill (propulsion or RCS failed), firepower kill (weapons failed), composite mission kill check
- **Damage History:** All damage events recorded with source, health delta, and status transitions
- **Heat Management:** Per-subsystem heat tracking with overheat penalties and passive dissipation
- **Combat System:** Coordinates truth weapons, integrates with targeting and power systems, tracks shots/hits/accuracy
- **Resupply:** Restores all weapon ammo to full capacity
- **Intercept Scenario:** YAML-based mission with win/fail conditions tied to mission kill status

## What Was Fixed (This Session)

- Railgun muzzle velocity corrected: 5 km/s -> 20 km/s (matches design doc)
- Railgun effective range corrected: 75 km -> 500 km (matches design doc)
- PDC muzzle velocity corrected: 1.2 km/s -> 3 km/s (matches design doc)
- Weapon names updated to "UNE-440 Railgun" and "Narwhal-III PDC"
- Added TRACKING state to LockState enum; lock now starts at TRACKING instead of ACQUIRING
- Added track_quality that degrades with range and target acceleration
- Added confidence field to FiringSolution (0-1, combines track quality and range accuracy)
- Both weapons now target all 5 subsystems (propulsion, rcs, sensors, weapons, power)
- Lock loss reverts to TRACKING state instead of NONE

## What's Still Missing

- **Firing arcs:** `in_arc` is always `True`; turret azimuth/elevation limits from Hardpoint not enforced by TruthWeapon
- **Charge time:** Railgun defines `charge_time=2.0` but `fire()` does not enforce a charge-up delay
- **Burst fire:** PDC defines `burst_count=5` / `burst_delay=0.05` but `fire()` only fires a single round per call
- **CONTACT state:** `LockState.CONTACT` exists in the enum but is never entered by any code path

## Architecture Notes

The combat system is split across four key modules:

- `hybrid/systems/weapons/truth_weapons.py` -- Physics-based `TruthWeapon` class with `WeaponSpecs`, `FiringSolution`, and ballistic intercept math. Factory functions `create_railgun()` / `create_pdc()` build pre-configured instances.
- `hybrid/systems/targeting/targeting_system.py` -- `TargetingSystem` manages the lock state machine, track quality computation, and firing solution distribution to weapons. Reads sensor contacts and damage model to degrade tracking.
- `hybrid/systems/combat/combat_system.py` -- `CombatSystem` owns the truth weapon collection, coordinates firing with power and targeting systems, and tracks engagement statistics.
- `hybrid/systems/damage_model.py` -- `DamageModel` with per-subsystem `SubsystemHealth`, status progression, mission kill detection, heat management, and combat summary reporting.

The legacy `WeaponSystem` in `weapon_system.py` is retained for backward compatibility but is separate from the truth weapon pipeline.
