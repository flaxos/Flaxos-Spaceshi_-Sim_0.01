# Developer Guide

## Adding a New Reactor Type
1. Edit `hybrid/core/constants.py` to add default values if needed.
2. In `hybrid/systems/power/reactor.py`, modify the `Reactor` class if you need specialized behavior (e.g., different thermal curves).
3. Update ship JSON to include `"power": {"primary": {"capacity": X, "output_rate": Y, "thermal_limit": Z}, ...}`.

## Adding a New Weapon Class
1. In `hybrid/systems/weapons/weapon_system.py`, subclass `Weapon` or modify power/heat behavior.
2. Update your ship’s JSON under:
   ```json
   "weapons": {
     "weapons": [
       {
         "name": "plasma_cannon",
         "power_cost": 20.0,
         "max_heat": 75.0,
         "ammo": 50
       }
     ]
   }
   ```
Mount it via a hardpoint in:
```json
"hardpoints": [
  {
    "id": "hp1",
    "type": "turret",
    "weapon": "plasma_cannon"
  }
]
```

## Adding New Modules
Fleet Logic → hybrid/systems/fleet/…

Launch Bay → hybrid/systems/launch/…

New GUI Components → hybrid/gui/widgets/…

## File Structure Reference
```
hybrid/
  core/
    event_bus.py
    base_system.py
    constants.py
  systems/
    power/
      reactor.py
      management.py
    weapons/
      weapon_system.py
      hardpoint.py
    navigation/
      navigation.py
    sensors/
      sensor_system.py
    simulation.py
  cli/
    run_cli.py
  gui/
    run_gui.py
tests/
  core/
    test_event_bus.py
  systems/
    power/
      test_reactor.py
      test_management.py
    weapons/
      test_weapon_system.py
      test_hardpoint.py
  hybrid_tests/
    test_ship_initialization.py
README.md
GUIDE.md
```
