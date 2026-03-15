# FLAXOS NAVAL OPERATIONS MANUAL

### United Nations Earth Naval Command
### Bridge Operations & Combat Doctrine
### Edition 3.1 — Restricted Distribution

---

> *"Space is not forgiving. It does not care about your intentions, your training, or your experience. It enforces Newton's laws with absolute consistency. The crews who survive are the ones who internalize those laws until they become instinct."*
>
> — Senior Instructor Maris Venn, UNEC Combat Training Division

---

## Foreword

This manual is written for new bridge officers reporting to their first assignment aboard a UNEC warship. If you are reading this, you have already passed the Academy's entrance examinations. What the Academy tested was aptitude. What this manual teaches is competence.

You will notice that this manual does not describe weapons as "powerful" or tactics as "decisive." Those words belong in recruitment materials. This manual describes *mechanisms*: how sensors work, why heat matters, what happens when a tungsten penetrator passes through composite cermet armor at 20 kilometres per second. Understanding the mechanism is the only path to reliable performance under pressure.

A few ground rules before we begin:

**Understand the physics, not the buttons.** Knowing which button fires the railgun is the minimum. Knowing *when* to fire, *why* your firing solution has 60% confidence, and *what* happens if you miss — that is competence.

**There are no HP bars.** Your ship does not have a health bar that depletes to zero. Your ship has systems. Those systems can be degraded, impaired, or destroyed. When enough critical systems fail, the ship becomes non-functional — a "mission kill." Victory is achieved by mission-killing the enemy, not by reducing an arbitrary number to zero.

**Heat is always there.** Every system on this ship generates waste heat. The reactor, the drive, the weapons, the sensors. That heat must go somewhere. If your radiators fail or your crew ignores the thermal panel, the ship will overheat and shut itself down at the worst possible moment. You will not be warned gently.

Read this manual. Understand it. Then forget you ever read it and fly the ship until these concepts live in your hands.

---

## Chapter 1: Bridge Operations

### 1.1 The Bridge Concept

A warship is too complex for one person to operate effectively in combat. The bridge is divided into stations, each responsible for a domain of ship function. Each station has specific commands it can issue and specific telemetry it receives. A crew member at Tactical cannot issue helm commands — that is a feature, not a limitation. Clear authority prevents conflicting inputs at critical moments.

### 1.2 Bridge Stations

| Station | Domain | Brief Role |
|---------|--------|-----------|
| **Captain** | All | Command authority. Can issue any command to any system. Can override any station. |
| **Helm** | Navigation & Flight | Controls thrust, heading, autopilot programs, and docking maneuvers. |
| **Tactical** | Weapons & ECM | Manages the targeting pipeline, fires all weapons, operates electronic warfare. |
| **OPS** | Power & Damage | Manages power allocation, dispatches repair crews, manages thermal systems. |
| **Engineering** | Reactor & Propulsion | Controls reactor output, drive throttle, radiators, fuel monitoring. |
| **Comms** | Communications & IFF | Manages IFF transponder, radio channels, distress beacon. |
| **Science** | Sensors & Analysis | Operates active sensors, classifies contacts, analyzes signatures. |
| **Fleet Commander** | Multi-Ship | Coordinates fleet movements, formations, shared targeting, fire coordination. |

### 1.3 Chain of Command

The **Captain** station has full authority over all other stations. The Captain can issue any command without claiming ownership of a specific station. In practice, a competent captain spends more time listening to their crew than issuing commands — the specialists at each station know their domain better than the person trying to manage all of them simultaneously.

Each non-Captain station operates within its domain. Commands issued outside a station's authority are rejected. This is enforced at the server level — there is no override in the GUI.

**Station override rules**: The Captain can override any station. The Fleet Commander can override Tactical and Comms. No other overrides exist.

### 1.4 Telemetry

Each station receives a filtered subset of ship telemetry relevant to its role. Helm sees navigation data: position, velocity, fuel status, autopilot state. Tactical sees weapons status, targeting data, and threat board. OPS sees power grid, system health, damage reports. No station is overwhelmed with data outside its domain.

All stations receive emergency alerts regardless of domain — hull breach, reactor overheat, incoming torpedo.

### 1.5 Claiming a Station

When you connect to the server, you must claim a station before issuing commands. In the GUI, this is done through the station selector in the bridge controls bar. In a multi-crew session, only one player may hold each station at a time. The Captain station is always available regardless of how many other stations are claimed.

---

## Chapter 2: Navigation and Helm

### 2.1 Newtonian Flight

This ship does not fly like an aircraft. There is no lift, no drag, no atmosphere. In vacuum, the only forces acting on your ship are thrust from your engines and gravitational attraction from nearby massive bodies.

Newton's second law: **F = ma**. Force equals mass times acceleration. Your drives provide a fixed thrust force. Your ship's total mass (dry mass plus remaining fuel and ammunition) determines how much you accelerate. As you burn fuel and fire weapons, your mass decreases — your acceleration for the same thrust increases.

The consequences of this are not intuitive if you come from an atmospheric background:

- **You do not stop when you cut the engines.** In vacuum, a ship with engines off continues at its current velocity forever. "Stopping" requires burning in the opposite direction.
- **Your velocity is not your heading.** You can be moving toward a target while pointed directly away from it.
- **Turns consume delta-v.** Changing direction is expensive. A turn is not free.

### 2.2 Flip-and-Burn

The standard interplanetary maneuver is flip-and-burn: accelerate toward your destination until the halfway point, flip 180 degrees, then decelerate for the second half. This maximizes travel speed while ensuring you arrive at a manageable velocity.

In combat, flip-and-burn is modified. You rarely have time for a clean deceleration arc when a hostile is actively maneuvering. The Helm station's `flip_and_burn` command executes an automated version — it calculates the flip point and schedules the deceleration burn. Use `set_course` with a target position for the flight computer to plan the full trajectory.

### 2.3 Delta-V Budget

Delta-v is the total velocity change your ship can achieve with its remaining fuel. It is calculated from the Tsiolkovsky rocket equation:

```
delta_v = ISP * g0 * ln(wet_mass / dry_mass)
```

Where ISP is the specific impulse of your drive (seconds), `g0` is 9.81 m/s², wet mass is your current total mass, and dry mass is your empty mass. This is the fundamental currency of spaceflight. You have a finite amount of it, and spending it poorly is fatal.

Monitor your fuel status on the Helm view's Flight Data panel. The remaining delta-v display tells you exactly how much maneuver budget you have left. A ship that has expended its delta-v budget cannot intercept, evade, or return to port.

### 2.4 The RCS and Attitude Control

Attitude (your ship's orientation) is controlled by the Reaction Control System — small thrusters positioned fore and aft that generate torque. The RCS does not propel you through space; it rotates you in place.

Torque = I × angular_acceleration

Your ship has a moment of inertia proportional to its mass and size. Larger ships rotate more slowly for the same RCS torque. A corvette can snap its nose around in seconds; a cruiser requires careful planning for attitude changes.

The Helm station's RCS panel allows manual attitude control. The autopilot uses RCS automatically when executing maneuver programs.

**If RCS is destroyed**, you cannot change your orientation. You may still have main drive thrust, but you cannot aim it. This is a severe tactical situation.

### 2.5 Autopilot Programs

The flight computer offers several autopilot programs. Each executes automatically once engaged. Helm override commands (manual thrust or heading input) disengage the autopilot immediately.

| Program | Command | Description |
|---------|---------|-------------|
| **Intercept** | `autopilot intercept <target>` | Intercepts a moving target using proportional navigation. Phases: intercept → approach (10 km) → match velocity (1 km). |
| **Go To Position** | `set_course <x> <y> <z>` | Navigates to an absolute position. Used by the `flight_computer` panel with flip-and-burn planning. |
| **Match Velocity** | `autopilot match <target>` | Matches velocity with a target ship. Useful for formation keeping and docking approach. |
| **Hold Position** | `autopilot hold` | Cancels velocity relative to a reference frame and holds position. |
| **Orbit** | `autopilot orbit <target>` | Maintains a circular orbit around a target at specified radius. |
| **Rendezvous** | `autopilot rendezvous <target>` | Three-phase approach: close, approach, match velocity. Designed for docking. |
| **Formation** | `autopilot formation <lead>` | Maintains position relative to a lead ship. |
| **Evasive** | `autopilot evasive` | Random jinking maneuvers to degrade enemy targeting. Consumes delta-v rapidly. |
| **Off** | `autopilot off` | Disengage all autopilot programs. |

**Intercept approach phases**: When closing on a target, the intercept autopilot transitions through three phases automatically. Beyond 10 km it burns hard on a lead pursuit. Between 10 km and 1 km it throttles to a maximum approach speed of 100 m/s to avoid overshooting. Inside 1 km it switches to match-velocity mode to stabilize relative motion.

### 2.6 Cold Drift

Cold drift is a low-emission flight mode: main drive off, RCS at minimum, active sensors silenced. The ship coasts on its current velocity vector with minimal IR and radar signature.

Command: `cold_drift` (Helm or OPS station)
Exit: `exit_cold_drift`

In cold drift, you cannot accelerate. You can only observe and wait. It is used for stealth approaches, ambushes, and emergency thermal management when the ship is overheating. A cold-drifting ship is much harder to detect on passive sensors — but it is also a target that cannot maneuver if discovered.

### 2.7 Docking

Docking requires precise velocity matching and positional alignment. The `request_docking` command initiates an automated docking approach sequence that transitions through rendezvous phases. Do not attempt manual docking without the autopilot unless you are at very close range with near-zero relative velocity.

---

## Chapter 3: Tactical Operations

### 3.1 The Targeting Pipeline

Every weapon system on this ship requires a firing solution before it can engage. A firing solution is a calculated prediction of where the target will be when your projectile arrives. At 20 km/s, a railgun round takes 5 seconds to cross 100 km. In those 5 seconds, your target is maneuvering. Firing at where they are is not the same as firing at where they will be.

The targeting pipeline has five stages:

```
CONTACT --> TRACKING --> ACQUIRING --> LOCKED --> FIRING SOLUTION
```

**Contact**: Sensors detect an IR or radar return. You know something is there. You have a bearing and approximate range. You do not know if it is friendly, hostile, or a piece of debris.

**Tracking**: The Tactical officer designates the contact (`designate_target` command). Fire control begins actively tracking — correlating successive position reports to build a velocity estimate. Track quality is a number from 0 to 100. It degrades with range (sensors are less precise at distance), with target acceleration (a maneuvering target is harder to predict), and with your own sensor degradation.

**Acquiring**: The fire control computer is refining the track to sufficient precision for ballistic solutions. This takes time — the `lock_time` value from your ship's targeting system specification. A corvette achieves lock in 2 seconds. A cruiser with its advanced targeting suite achieves lock in 1 second.

**Locked**: Full fire control lock. The track is stable enough to compute firing solutions for each available weapon.

**Firing Solution**: For each weapon, the computer calculates a lead angle and expresses it as a confidence score. 100% means the geometry is perfect — point-blank, stationary target, perfect sensors. 50% means significant uncertainty in the prediction; many shots at this confidence will miss. Below 30%, the fire control computer considers the solution unreliable.

Lock can be **LOST** if the target maneuvers aggressively, crosses behind an obstacle, or your sensors are degraded mid-engagement. The system will attempt automatic reacquisition, but this takes time.

### 3.2 Requesting a Solution

Once locked, use `request_solution` to compute the current firing solution. The response includes:

- Confidence score (0–100%)
- Recommended weapon
- Time of flight to target
- Lead angle
- Estimated hit probability per weapon type

Request a new solution before each shot if the tactical situation has changed significantly. A firing solution computed 30 seconds ago against a target that has since changed heading is worth nothing.

### 3.3 Target Subsystem Selection

The `set_target_subsystem` command tells the fire control computer *which subsystem to aim for* on the target. Available subsystems are: propulsion, rcs, sensors, weapons, targeting, reactor, life_support, radiators.

This matters because **hit location is physically determined**. The fire control computer adjusts the aim point to target a specific section of the enemy ship. Aiming for propulsion means trying to hit the aft section. Aiming for sensors means trying to hit the fore section. The actual penetration point depends on armor angle, impact velocity, and armor thickness at that section — but you are telling the computer what you are trying to hit.

**Doctrine**: In most engagements, the priority is mission kill. Target propulsion to immobilize the enemy. Target sensors to blind them. Only target the reactor if you intend destruction rather than capture or mission kill.

### 3.4 Fire Control

With a valid lock and firing solution:

- `fire_railgun` — charges the UNE-440 and fires a single round (2-second charge, 5-second cycle)
- `fire_pdc` — fires a burst from the Narwhal-III PDC (auto-turret mode) or specifies a target
- `launch_torpedo` — launches a self-guided torpedo
- `fire_all` — fires all available weapons at the current lock

The fire control computer will reject a fire command if: no lock exists, the weapon is in cooldown, the weapon is out of ammo, power is insufficient, or the target is outside the weapon's firing arc.

Firing arc restrictions are physical. The railgun has a limited traversal — ±30 degrees azimuth, ±20 degrees elevation from the ship centerline. If the target is outside that arc, you must maneuver the ship to bring it into the cone before you can fire.

### 3.5 Weapon Status

`combat_status` and `weapon_status` commands return current ammunition counts, weapon health, charge states, and arc alignment relative to the current target. Check these regularly. Running out of railgun ammunition in the middle of an engagement is an avoidable catastrophe.

---

## Chapter 4: Weapons Systems

### 4.1 The UNE-440 Railgun

The UNE-440 is an electromagnetic kinetic accelerator that launches a 5-kilogram tungsten penetrator at 20 km/s. It is not a guided weapon. It does not have a proximity fuze. It does not explode. It is a rod of tungsten moving very fast in a straight line.

At 20 km/s, kinetic energy = 1 MJ/kg × 5 kg = **1 billion joules**. For reference, that is equivalent to several hundred kilograms of high explosive. The penetrator does not need to explode. It needs only to hit.

**Strengths**:
- Extreme penetration — 1.5× armor penetration multiplier against composite cermet
- At 20 km/s, time of flight to 100 km is 5 seconds — short enough to maintain track quality
- High per-hit damage: 35 hull, 25 subsystem
- Each hit is directed at a specific subsystem (if `set_target_subsystem` is used)

**Weaknesses**:
- 5-second cycle time between shots (the capacitor bank must recharge)
- 2-second charge before firing — the ship is committed to the shot
- Only 20 rounds total
- 15 degrees/second tracking speed — slow for engaging fast-crossing targets
- Useless against close-in threats (5 seconds of flight time at 1 km range = 0.05 seconds, but the minimum effective range is 500 m)

**Tactical use**: Engage at medium to long range (50–300 km), where the round's speed is an advantage and PDCs are out of range. Shoot for propulsion or weapons. Fire deliberate shots — you have 20 rounds and no resupply in the field. A shot with 60% confidence is a question of whether 40% failure rate is acceptable given your remaining ammunition and the engagement timeline.

### 4.2 The Narwhal-III PDC

The Narwhal-III Point Defense Cannon is a high-rate-of-fire autocannon firing 50-gram rounds at 3 km/s. It is an auto-turret — the fire control computer aims and fires it automatically against designated threats. It can be manually designated to fire at a contact, but its primary role is autonomous point defense.

The PDC fires in 5-round bursts at 10 rounds per second. At that rate, it burns through 200 rounds in 20 seconds. A corvette carries 2,000 rounds total — enough for 10 magazines. A cruiser carries the same 2,000 rounds per PDC, with 8 PDCs.

**Strengths**:
- 120 degrees/second tracking — fast enough to engage incoming torpedoes
- Continuous suppression fire at close range
- Upper and lower hemisphere coverage on most ships
- Large ammo supply relative to engagement duration

**Weaknesses**:
- Effective only inside 5 km
- 0.5× armor penetration — cannot meaningfully damage armored warships
- Ammunition is finite and burns fast
- Minimal per-round damage (5 hull, 3 subsystem) — requires many rounds to matter against ships

**PDC modes**:
- **Point defense**: Automatic engagement of any incoming torpedo or missile within range. This is the default mode and should remain active at all times in a combat zone.
- **Anti-ship suppression**: Manual designation of a ship contact for PDC fire. At close range (under 2 km), PDC fire can accumulate meaningful damage through volume of fire. This is ammunition-expensive and should be used judiciously.

**Set PDC mode**: `set_pdc_mode auto` (point defense, default) or `set_pdc_mode manual` (requires explicit fire commands).

### 4.3 Torpedoes

Torpedoes are guided munitions with their own drive, fuel, and autonomous guidance computer. They are not ballistic — once launched, they maneuver independently toward the designated target. They can receive datalink updates from the launching ship to refine their guidance.

**Physics model**:
- 250 kg total mass (50 kg fragmentation warhead, 80 kg drive, 60 kg fuel, 60 kg structure)
- 8 kN thrust at launch, declining as fuel depletes
- ~32 m/s² initial acceleration — faster than most warships
- ~4,600 m/s total delta-v for terminal maneuvers
- Warhead: 50 kg fragmentation, lethal within 30 m, damaging to 100 m

**IR signature**: The torpedo drive produces a large IR plume. It is visible on passive sensors from launch. The enemy will see the torpedo coming. Their PDCs will attempt intercept. This is expected — torpedoes are not a surprise weapon. They are an attrition weapon: launch enough of them to saturate the enemy's PDC capacity.

**Terminal phase**: In the final seconds of approach, the torpedo's guidance transitions to terminal homing — maximizing closing rate and minimizing the PDC's intercept window. Head-on approaches give the PDC the least time to acquire and engage. Tail-chase approaches give the PDC more time.

**Countermeasures**: A single flare deployment can divert a torpedo if it breaks lock. Chaff is less effective — torpedoes use IR guidance, not radar. Concentrated PDC fire during the terminal phase is the primary defense.

**Tactical use**: Torpedoes are best used to saturate an enemy's defensive capacity. Launch multiple torpedoes simultaneously to divide PDC attention. Use railgun fire concurrently — the enemy must choose between defensive maneuvering against the railguns and holding position for PDC engagement of the torpedoes.

---

## Chapter 5: Sensor Operations

### 5.1 Passive Sensors

Passive sensors do not emit anything. They listen. Specifically, they detect infrared radiation — heat emitted by other ships.

Detection is emission-driven. The question is not "is the target within sensor range?" The question is "does the target's IR emission, at this distance, exceed the sensor's noise floor?"

The formula: **IR flux received = source_IR_power / (4π × distance²)**

This is the inverse-square law. Double the distance, receive one-quarter the IR flux. A ship burning at 100% thrust with its reactor running hot has an IR signature that can be detected at extreme range. A ship in cold drift — drive off, radiators minimized — has a much smaller signature and may only become detectable at close range.

**What generates IR signature**:
- Main drive: dominant source, proportional to thrust level
- Reactor: continuous output even at idle
- Radiators: always emitting to dump waste heat
- Weapons fire: brief spikes during railgun discharge
- Active sensor pings: detectable emissions

**Reducing IR signature**:
- Reduce thrust (or cut drive entirely)
- Enter EMCON mode (70% IR reduction)
- Use cold drift
- Damage to radiators paradoxically *increases* IR signature (heat builds up inside the ship and must eventually escape)

**Passive sensor range by class**:
- Corvette: 30 km passive range
- Frigate: 40 km passive range
- Destroyer: 50 km passive range
- Cruiser: 80 km passive range

These are hardware upper bounds — a very bright target (thrusting hard) may be detectable from much further. A very cold target (cold drifting) may only appear near the hardware minimum.

### 5.2 Active Sensors

Active sensors emit a radar pulse and listen for the return. They can detect targets regardless of thermal signature — a cold-drifting ship has a radar cross section (RCS) that remains constant regardless of drive activity.

**Active sensor ranges**:
- Corvette: 60 km active scan range
- Frigate: 80 km active scan range
- Destroyer: 100 km active scan range
- Cruiser: 150 km active scan range

Active sensors have a cooldown after each ping (3–5 seconds depending on class). They cannot be used continuously.

**Critical limitation**: Active sensors emit. A ship with active radar pinging is broadcasting its presence and position to everyone with a receiver. The Science station of any ship within range can detect your ping. Use active sensors when you need precise range/track data and accept the signature cost, not as a substitute for passive observation.

The Science station commands `ping_sensors` and `analyze_contact` operate in this domain.

### 5.3 Contact Management

When sensors detect a target, it becomes a **contact** with a stable ID (e.g., `C001`). The contact tracker maintains this ID even through periods of low confidence or temporary loss of detection.

**Contact states**:
- **Detected**: IR or radar return observed, position and approximate range known
- **Tracked**: Multiple detections correlated into a track — velocity estimate available
- **Named**: Confidence above 50% — classification available (IFF transponder data, signature analysis)

Contact confidence is a 0–100% score. It degrades by 20% per missed scan rather than dropping instantly. At 0%, the contact is lost — but the track history is retained for reacquisition when the contact re-appears.

The Science station `analyze_contact` command refines classification — determining if a contact is military, civilian, which class, which faction. This information feeds into tactical threat assessment.

### 5.4 Emissions Control (EMCON)

EMCON is an operating posture, not a specific system. When EMCON is active:
- Active sensors shut down (no radar pings)
- Own IR signature reduced by 70% (EMCON multiplier: 0.3 of normal)
- Own radar cross section reduced by ~30% (cannot change hull shape, but active emitters go silent)

The cost: you can only passively observe. Your contact picture degrades to what passive sensors can provide. If the enemy is in cold drift, you may lose them entirely.

EMCON is set by Tactical, OPS, or Comms station: `set_emcon active` / `set_emcon inactive`.

---

## Chapter 6: Engineering and Damage Control

### 6.1 The Subsystem Model

Your ship is not a single object with a health bar. It is an assembly of interdependent systems, each with its own health value. When systems take damage, they degrade. When they degrade enough, they fail. When they fail, everything that depended on them degrades.

**Tracked subsystems**:

| System | Location | Function |
|--------|----------|---------|
| **Reactor** | Aft, midship | Powers all other systems |
| **Propulsion** | Aft | Main drive thrust |
| **RCS** | Fore and aft | Attitude control, rotation |
| **Sensors** | Fore | Passive and active detection |
| **Targeting** | Fore, midship | Fire control lock and solutions |
| **Weapons** | Fore | Railgun and PDC operation |
| **Life Support** | Midship | Crew habitability |
| **Radiators** | Midship, external | Thermal management |

**Health thresholds**: Each subsystem has a maximum health and a failure threshold (typically 20% of max health). Above the failure threshold: full performance. Below it: degraded performance. At zero: offline.

**Hit location**: Damage location is determined by the projectile's velocity vector and the target ship's orientation. A round fired from directly ahead strikes the fore section — where sensors, targeting, and weapons are located. A round fired from astern strikes the aft section — where propulsion and reactor live. Armor thickness varies by section.

### 6.2 Cascade Effects

Subsystem failures do not occur in isolation. The dependency graph:

```
Reactor --> Propulsion (power)
Reactor --> RCS (power)
Reactor --> Sensors (power)
Reactor --> Weapons (power)
Reactor --> Targeting (power)
Reactor --> Life Support (power)

Sensors --> Targeting (track quality)
RCS --> Targeting (aim stability)
```

When the reactor is **damaged** (below failure threshold), all dependent systems operate at ~50% capacity. When it is **destroyed**, they lose power entirely.

When sensors are destroyed, the targeting system cannot build new tracks. Existing locks will be lost as they degrade without update. When RCS is destroyed, targeting solutions degrade because the ship can no longer hold a steady aim.

The cascade effects are **performance penalties**, not additional damage. A 50% penalty from reactor damage means your drive produces 50% of normal thrust — it does not mean the drive takes additional damage.

**What this means in practice**: A single railgun hit to the aft section can:
1. Damage propulsion directly (penetration nearest propulsion)
2. If the reactor takes any damage, cascade to everything
3. Reduce acceleration, degrade sensors, reduce targeting quality
4. Produce a positive feedback loop where degraded systems are harder to use to repair the situation

### 6.3 Repair

The OPS station dispatches repair crews: `dispatch_repair <system>`. Repair is not instant. It takes time proportional to the damage severity and the system's criticality value. The repair queue is managed by OPS.

**Repair priority doctrine**:
1. Reactor (restores power to everything)
2. Life Support (crew survival)
3. Propulsion (restores mobility)
4. RCS (restores maneuver)
5. Sensors (restores situational awareness)
6. Targeting (restores fire control)
7. Weapons (restores offensive capability)
8. Radiators (prevents overheating cascade)

This order is guidance, not law. Tactical situation may invert priorities — if sensors are destroyed in an ongoing engagement, restoring them may take precedence over propulsion repair if you are not immediately threatened with collision.

### 6.4 Thermal Management

Heat is the invisible enemy. Every system generates waste heat. The thermal system integrates heat over time and attempts to radiate it through your radiator array.

**Stefan-Boltzmann radiation**:
```
P_radiated = emissivity * sigma * area * (T_hull^4 - T_space^4)
```

Where sigma = 5.67e-8 W/m²/K⁴ and T_space = 2.7 K. This means:
- Radiating capacity increases sharply with temperature
- A hotter ship radiates more effectively — to a point
- Radiator area is a multiplier on all of this

**Heat sources per tick**:
- Reactor idle: 20 kW continuous
- Reactor at full load: up to 200 kW
- Main drive: ~2% of thrust power (capped at 100 kW)
- Active sensor cycle: 5 kW
- Railgun discharge: spike per shot

**Temperature thresholds**:
- 300 K: Nominal operating temperature
- 400 K: Warning — systems begin throttling. The drive output will reduce. Weapons may refuse to charge.
- 500 K: Emergency — forced system shutdowns. The reactor may scram. At this point, the ship is in a crisis that will get worse before it gets better, because the radiators (now running hotter) radiate more — but if they are damaged, the effective area is reduced.

**Radiator damage**: Radiators are external, exposed hardware. They are typically the first things struck by fragmentation damage. As radiator health falls, effective radiating area decreases proportionally. A ship with 50% radiator health can only dissipate half the heat it could at full capacity.

**Heat sink**: Some ships carry an expendable heat sink — a block of phase-change material that can absorb heat at high rate for a limited time. The OPS or Engineering station activates it: `activate_heat_sink`. It is an emergency measure, not a solution. When the heat sink is saturated, it must be deactivated or it will melt.

**Practical thermal doctrine**:
- Monitor the thermal panel continuously during combat
- Reduce thrust if temperature approaches warning threshold
- Repair radiators before they become a cascade failure point
- Use cold drift for thermal recovery if not immediately threatened
- Never ignore a rising temperature reading. It will not fix itself.

---

## Chapter 7: Electronic Warfare

### 7.1 What ECM Is and Is Not

Electronic countermeasures degrade the *enemy's ability to target you*. This is a precise statement. ECM does not make you invisible. It does not prevent detection. It injects noise into their tracking systems, degrades their confidence scores, and makes their firing solutions less reliable.

The enemy's sensors still work. Their fire control still works. Their weapons still work. They just work *worse*. An enemy with an 80% firing solution confidence may drop to 40% when you are jamming them. That is meaningful — but it is not invulnerability.

### 7.2 Radar Jamming

The jammer broadcasts high-power radio frequency noise across sensor bands. The effect at the enemy's receiver follows inverse-square law:

```
Jamming_effectiveness = jammer_power / distance^2
```

At close range, a jammer can completely saturate an enemy radar receiver. At long range, the jamming effect diminishes significantly. This means jamming is most effective when you are close — which is also when you are in the most danger.

**Corvette jammer power**: 30,000 W
**Frigate/intercept scenario**: 50,000 W
**Destroyer**: 80,000 W

**Cost**: The jammer generates significant heat (10,000 W waste heat per second while active) and draws power. Sustained jamming in a prolonged engagement will stress your thermal system.

**Countermeasure**: Frequency hopping. Multi-spectral sensors can partially defeat single-band jamming by switching frequencies. Advanced sensor suites are less affected by jamming than baseline installations.

Command (Tactical or OPS): `activate_jammer` / `deactivate_jammer`

### 7.3 Chaff

Chaff is a bundle of radar-reflective metallic particles. When deployed, it creates a cloud that inflates your apparent radar cross section by a factor of 5× and adds random position noise to any radar-based track.

**Deployment**: `deploy_chaff`
**Duration**: ~30 seconds before the cloud disperses
**Ammo**: 6–12 bundles depending on ship class (corvette: 6)

Chaff works against radar-derived tracks. It does not help against IR/passive-thermal tracks. If the enemy is using purely passive sensors, chaff provides minimal benefit.

Use chaff when: closing inside radar lock range, being engaged by a railgun with high confidence, or to break an existing lock.

### 7.4 Flares

Flares are expendable IR sources that mimic a drive plume. Each flare emits approximately 5 megawatts of infrared radiation — comparable to a ship drive at moderate thrust.

**Deployment**: `deploy_flare`
**Duration**: ~8 seconds before burnout
**Ammo**: 8–12 depending on ship class (corvette: 8)

Flares are primarily effective against IR-guided weapons — specifically torpedoes homing on your drive signature. A timely flare deployment forces a torpedo's guidance system to choose between the flare's bright signal and your dimmer signature. If the torpedo switches to the flare, it misses.

The timing matters. Deploy flares when the torpedo is in its terminal phase — too early and the flare burns out before intercept; too late and the torpedo has already locked its final approach geometry.

### 7.5 EMCON (Emissions Control)

EMCON is the most powerful ECM tool and the most self-limiting. In EMCON:
- Own IR signature: reduced to 30% of normal (70% reduction)
- Own RCS: reduced to ~70% (minor — hull shape is fixed)
- Active sensors: offline
- Jammer: offline (jamming itself is an emission)

In EMCON, you are difficult to detect passively. But you are also nearly blind — limited to whatever passive contacts your sensors can build on thermal emissions alone. A target in cold drift may be invisible to you even at moderate range.

EMCON is tactically appropriate for:
- Stealth approach before an engagement
- Evasion after disengaging
- Emergency thermal management (cuts active system heat generation)
- Ambush positioning

It is inappropriate when you need to maintain a targeting lock, engage with radar-dependent weapons, or coordinate with fleet elements.

---

## Chapter 8: Combat Tactics

### 8.1 Engagement Range Selection

Not all ranges are equally favorable. Understand the engagement envelope before closing:

**Extreme range (300–500 km)**: Railgun only. Time of flight is 15–25 seconds. Track quality at this range is poor — any target maneuver in those 25 seconds invalidates the firing solution. Shots at this range are speculative unless the target is on a predictable ballistic trajectory. Not recommended except for harassment.

**Long range (100–300 km)**: Railgun primary. Time of flight 5–15 seconds. Track quality is marginal for a maneuvering target. Good against non-maneuvering or lightly maneuvering targets. Torpedoes launched at this range give the enemy maximum time to prepare defenses.

**Medium range (20–100 km)**: Railgun optimal zone. Time of flight under 5 seconds. Track quality is good. Firing solution confidence is high if the target isn't maneuvering aggressively. Torpedo launch at this range is standard — the torpedo has enough delta-v to maneuver but not so much time that PDCs can acquire multiple intercept opportunities.

**Close range (5–20 km)**: Railgun and torpedo convergence zone. Both weapons are effective. PDC begins to have some defensive value at the near end of this range. Engagement dynamics accelerate significantly — mistakes are hard to recover from.

**Point blank (0–5 km)**: PDC territory. Railguns still function but at very high confidence (point-blank solutions are easy). PDC fire can accumulate damage at this range. Torpedo launch is dangerous to the launching ship if the target is close. Closing to this range with an intact enemy is a high-risk decision.

### 8.2 Approach Vectors

The geometry of your approach affects which of your weapons bear, which enemy weapons bear, and which section of your armor faces the threat.

**Head-on approach**: Your fore section (strongest armor on most ships) faces the threat. Your railgun has the best firing arc. The enemy's railgun is pointing at you. You are the hardest target for their torpedoes to engage (high closing speed = short PDC intercept window) but also the most exposed to their railgun.

**Beam approach (perpendicular)**: You present the broadest sensor target. Your railgun may not bear (±30 degrees azimuth). The enemy can fire on your less-armored port/starboard sections. Not recommended for closure.

**Oblique approach (30–45 degrees off centerline)**: Compromise. Your fore armor is partially presented. Your railgun can bear if the target is within the 30-degree arc. This is the standard combat approach vector.

**Aft presentation**: Your propulsion and reactor are facing the enemy. Your weakest armor. Your railgun cannot bear. Do not present your aft to a threat.

### 8.3 Mission Kill Doctrine

The objective in most engagements is not destruction — it is *mission kill*. A mission-killed ship cannot complete its objective. It may still be intact, but it cannot threaten you. This matters for three reasons:

1. It takes fewer rounds. Destroying a ship requires degrading every system until hull integrity collapses. Mission-killing requires destroying one or two critical systems.

2. It preserves evidence and salvage. A destroyed ship is debris. A mission-killed ship can be captured, boarded, and examined.

3. It reduces collateral damage. In scenarios involving neutral or civilian ships, a mission kill that immobilizes the target without destroying it may be the only legally sanctioned option.

**Mission kill targets by priority**:

| Priority | Target | Effect |
|----------|--------|--------|
| 1 | Propulsion | Ship cannot maneuver or escape |
| 2 | Reactor | All systems lose power (may be lethal) |
| 3 | Sensors | Ship is blind — cannot target or navigate precisely |
| 4 | RCS | Ship cannot orient weapons or drive |
| 5 | Weapons | Ship cannot engage offensively |

For the intercept scenario (corvette vs. corvette or frigate vs. corvette), the standard doctrine is: **target propulsion first**. An immobilized corvette is a solved problem. It cannot escape, cannot maneuver to improve its firing solutions, and its tactical options collapse to static defense. Once propulsion is destroyed, it is a question of how long you want to spend finishing the engagement.

### 8.4 Recognizing When to Disengage

Aggression is not always the correct choice. Recognize when the tactical situation has turned against you:

**Disengage if**:
- Your propulsion is impaired and the enemy still has mobility
- Your ammo is critically low and the enemy is not close to mission-killed
- Your reactor is damaged and you cannot sustain weapon fire
- Your sensors are down and you cannot maintain targeting lock
- The engagement is going to the enemy and you have a disengage vector

**Disengage procedure**:
1. Enter cold drift to reduce IR signature
2. Deploy chaff to break any active radar lock
3. Orient away from threat
4. Engage maximum thrust on the disengage vector
5. Activate EMCON once at range
6. Evaluate repair options before re-engagement

A ship that disengages and repairs lives to fight again. A ship that fights until destruction contributes nothing to its next engagement.

### 8.5 Electronic Warfare Integration

ECM is not a separate phase of combat — it is woven throughout the engagement:

**Pre-engagement**: EMCON while closing. Cold drift if thermal budget allows. Preserve your IR signature reduction until you commit to the approach.

**Opening engagement**: Deactivate EMCON to bring active sensors online and build targeting tracks. Launch torpedoes if within effective range. The torpedo drive plumes announce the engagement — stealth is over.

**Active exchange**: Jammer active if the range is short enough for effectiveness. Chaff on demand when taking railgun fire. Flares ready for torpedo terminal phase intercept. Monitor PDC ammunition — it depletes fast.

**Endgame**: If the enemy is mission-killed but still has sensors and weapons, maintain electronic pressure to degrade any remaining targeting capability. A blinded enemy cannot fire solutions.

---

## Appendix A: Ship Class Data

| Class | Length | Dry Mass | Max Fuel | Max Thrust | ISP | Passive Range | Active Range | Lock Time |
|-------|--------|----------|----------|-----------|-----|-------------|-------------|----------|
| **Corvette** | 30 m | 1,200 kg | 400 kg | 280 N | 3,500 s | 30 km | 60 km | 2.0 s |
| **Frigate** | 50 m | 2,200 kg | 700 kg | 380 N | 3,800 s | 40 km | 80 km | 1.5 s |
| **Destroyer** | 80 m | 4,000 kg | 1,200 kg | 450 N | 3,800 s | 50 km | 100 km | 1.2 s |
| **Cruiser** | 150 m | 12,000 kg | 4,000 kg | 700 N | 4,000 s | 80 km | 150 km | 1.0 s |
| **Freighter** | 120 m | 8,000 kg | 3,000 kg | 600 N | 4,200 s | — | — | — |

**Armor thickness (fore / aft / sides) — composite cermet unless noted**:

| Class | Fore | Aft | Port/Stbd | Dorsal/Ventral |
|-------|------|-----|----------|---------------|
| Corvette | 3.0 cm | 1.5 cm | 2.0 cm | 2.0 cm |
| Frigate | 5.0 cm | 2.5 cm | 3.5 cm | 3.0 cm |
| Destroyer | 8.0 cm | 4.0 cm | 6.0 cm | 5.0 cm |
| Cruiser | 12.0 cm | 6.0 cm | 8.0 cm | 7.0 cm |
| Freighter | 5.0 cm | 3.0 cm | 4.0 cm | 3.0 cm (steel composite) |

**Weapon loadouts**:

| Class | Railguns | PDCs | Torpedoes | Torpedo Capacity |
|-------|---------|------|-----------|----------------|
| Corvette | 1 | 2 | — | — |
| Frigate | 2 | 4 | — | — |
| Destroyer | 3 | 6 | 2 | 4 |
| Cruiser | 4 | 8 | 3 | 6 |
| Freighter | — | — | — | — |

**Crew complement**:

| Class | Minimum | Standard | Maximum |
|-------|---------|---------|--------|
| Corvette | 4 | 8 | 12 |
| Frigate | 10 | 25 | 35 |
| Destroyer | 20 | 45 | 60 |
| Cruiser | 50 | 120 | 180 |
| Freighter | 6 | 15 | 25 |

---

## Appendix B: Quick Reference Card

### Helm Station

```
Flight
  set_thrust <0.0-1.0>           Apply main drive thrust
  set_orientation <pitch> <yaw>  Set ship orientation
  cold_drift                     Enter low-emission drift mode
  exit_cold_drift                Resume normal operation

Autopilot
  autopilot intercept <target>   Intercept moving contact
  autopilot match <target>       Match velocity with contact
  autopilot hold                 Hold current position
  autopilot orbit <target>       Orbit target at set radius
  autopilot evasive              Random evasive jinking
  autopilot off                  Disengage autopilot
  set_course <x> <y> <z>        Navigate to position
  flip_and_burn                  Execute deceleration flip

Docking
  request_docking <target>       Begin docking approach sequence
  cancel_docking                 Abort docking
```

### Tactical Station

```
Targeting
  designate_target <contact_id>  Begin tracking contact
  set_target_subsystem <system>  Set aim point (propulsion/sensors/etc.)
  request_solution               Compute current firing solution
  lock_target <contact_id>       Acquire fire control lock
  unlock_target                  Release current lock

Weapons
  fire_railgun                   Charge and fire UNE-440
  fire_pdc [contact_id]          Fire PDC burst
  launch_torpedo                 Launch guided torpedo
  fire_all                       Fire all weapons at lock
  set_pdc_mode <auto|manual>     Set PDC operating mode
  ready_weapons                  Cycle weapons to standby
  combat_status                  View ammo counts and weapon state

ECM
  activate_jammer                Enable radar jammer
  deactivate_jammer              Disable radar jammer
  deploy_chaff                   Release chaff bundle
  deploy_flare                   Release IR flare
  set_emcon <active|inactive>    Toggle emissions control
  ecm_status                     View ECM system state
```

### OPS Station

```
Power
  set_power_profile <name>       Apply preset power configuration
  allocate_power <system> <pct>  Manually allocate power to system
  get_power_profiles             List available power profiles

Damage Control
  dispatch_repair <system>       Send repair crew to system
  report_status                  Full ship status report
  emergency_shutdown <system>    Emergency shutdown a system
  restart_system <system>        Restart a shut-down system

Thermal
  activate_heat_sink             Engage expendable heat sink
  deactivate_heat_sink           Disengage heat sink
  set_emcon <active|inactive>    Toggle EMCON (OPS authority)
```

### Engineering Station

```
  set_reactor_output <0.0-1.0>   Set reactor power level
  throttle_drive <0.0-1.0>       Set drive throttle
  manage_radiators <state>       Configure radiator deployment
  monitor_fuel                   Fuel and delta-v status
  emergency_vent                 Emergency thermal venting
  dispatch_repair <system>       Dispatch repair crews
  activate_heat_sink             Engage heat sink
```

### Science Station

```
  ping_sensors                   Active radar scan
  analyze_contact <contact_id>   Detailed signature analysis
  spectral_analysis <contact_id> Spectral signature breakdown
  estimate_mass <contact_id>     Estimate target mass from signature
  assess_threat <contact_id>     Threat classification
  science_status                 Sensor system status
```

### Comms Station

```
  set_transponder <mode>         IFF transponder mode
  hail_contact <contact_id>      Open communication channel
  broadcast_message <text>       Broadcast on open channel
  set_distress <true|false>      Distress beacon
  comms_status                   Comms system state
  set_emcon <active|inactive>    EMCON (Comms authority)
```

### Fleet Commander Station

```
  fleet_create <name>            Create new fleet
  fleet_add_ship <id>            Add ship to fleet
  fleet_form <formation>         Set fleet formation
  fleet_break_formation          Break formation
  fleet_target <contact_id>      Designate fleet target
  fleet_fire                     Fleet coordinated fire
  fleet_cease_fire               Cease fleet fire
  fleet_maneuver <params>        Coordinated fleet maneuver
  fleet_status                   Fleet overview
  share_contact <contact_id>     Share contact data with fleet
```

---

*End of Manual. Issued under UNEC Naval Publication Authority. Classification: Restricted.*

*"Know your ship. Know your weapons. Know your enemy's ship. The rest is arithmetic."*
