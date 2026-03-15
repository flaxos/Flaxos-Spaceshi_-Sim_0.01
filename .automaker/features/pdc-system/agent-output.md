

I'll review the current state of the PDC system implementation and continue from where the previous attempt left off. Let me start by understanding what's already been done.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "in_progress",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Identify gaps and missing pieces",
      "status": "pending",
      "activeForm": "Identifying gaps and missing pieces"
    },
    {
      "content": "Implement remaining PDC functionality",
      "status": "pending",
      "activeForm": "Implementing remaining PDC functionality"
    },
    {
      "content": "Verify PDC system works correctly",
      "status": "pending",
      "activeForm": "Verifying PDC system works correctly"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}
Let me explore the codebase to understand the current state of the PDC system.

🔧 Tool: Task
Input: {
  "description": "Explore PDC system state",
  "prompt": "Explore the current state of the PDC (Point Defense Cannon) system in this spaceship sim codebase. I need to understand:\n\n1. What PDC-related files and code already exist\n2. How the combat system is structured (look at hybrid/systems/ for combat-related files)\n3. How weapons are currently defined and handled\n4. The targeting pipeline and how weapons fire\n5. How projectiles/rounds are tracked\n6. The current weapon specs and configuration\n\nSearch thoroughly for:\n- Any files mentioning \"pdc\" or \"PDC\" or \"point_defense\" or \"narwhal\"\n- The combat system files (hybrid/systems/combat*.py)\n- Weapon-related files\n- The targeting system\n- Projectile tracking\n- Ship weapon configuration in ship_classes/ JSON files\n- The command handler for weapon commands\n\nGive me a comprehensive report of what exists and what might be missing for a full PDC implementation.",
  "subagent_type": "Explore"
}

🔧 Tool: Bash
Input: {
  "command": "find /projects/spaceship-sim -type f -name \"*.py\" | grep -E \"(combat|weapon|pdc|fire|target)\" | head -20"
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"PDC\\|pdc\\|point.defense\\|narwhal\" /projects/spaceship-sim --include=\"*.py\" --include=\"*.json\" -l 2>/dev/null | grep -v \".venv\" | sort"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/weapon_system.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/targeting/targeting_system.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/projectile_manager.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/hardpoint.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/command_handler.py",
  "limit": 100
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/ship_classes/corvette.json"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/commands/weapon_commands.py"
}

🔧 Tool: Bash
Input: {
  "command": "grep -n \"fire\" /projects/spaceship-sim/server/stations/station_types.py | head -30"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/server/stations/station_types.py",
  "limit": 150
}

🔧 Tool: Bash
Input: {
  "command": "find /projects/spaceship-sim -type f -name \"*.json\" -path \"*scenarios*\" | head -5"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/scenarios/intercept_scenario.json",
  "limit": 80
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/tests/systems/combat/test_combat_system.py",
  "limit": 100
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"reload\\|magazine\\|magazine_size\" /projects/spaceship-sim/hybrid --include=\"*.py\" -n | head -20"
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"armor\\|penetration\\|armor_penetration\" /projects/spaceship-sim/hybrid --include=\"*.py\" -n | head -20"
}

🔧 Tool: Bash
Input: {
  "command": "find /projects/spaceship-sim/hybrid -name \"*damage*\" -type f"
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"firing_arc\\|turret\\|arc_limits\" /projects/spaceship-sim/hybrid --include=\"*.py\" -l"
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"in_arc\\|firing.arc\" /projects/spaceship-sim/hybrid --include=\"*.py\" -n | head -10"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/damage_model.py",
  "limit": 150
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"burst\\|burst_count\\|burst_delay\" /projects/spaceship-sim/hybrid --include=\"*.py\" -n"
}

🔧 Tool: Bash
Input: {
  "command": "find /projects/spaceship-sim/gui -name \"*.js\" | grep -E \"(weapon|combat|pdc|tactical)\" | head -10"
}

🔧 Tool: Bash
Input: {
  "command": "ls -la /projects/spaceship-sim/gui/components/ | grep -E \"(weapon|tactical|combat)\""
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/gui/components/weapons-status.js",
  "limit": 100
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"TODO\\|FIXME\\|XXX\" /projects/spaceship-sim/hybrid/systems/weapons/ /projects/spaceship-sim/hybrid/systems/combat/ --include=\"*.py\" -n"
}

🔧 Tool: Bash
Input: {
  "command": "grep -r \"burst\" /projects/spaceship-sim --include=\"*.py\" -n | grep -i \"todo\\|implement\\|missing\" | head -10"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/.automaker/features/pdc-system/feature.json"
}

🔧 Tool: Bash
Input: {
  "command": "find /projects/spaceship-sim -type f -name \"*.py\" -path \"*/hybrid/systems/combat/*\" -o -path \"*/hybrid/systems/weapons/*\" | sort"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_log.py",
  "limit": 100
}
Good, the PDC system is largely implemented. Let me now look at the specific TODO items and the key files that need work.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "in_progress",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "pending",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "pending",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Verify PDC system works correctly with tests",
      "status": "pending",
      "activeForm": "Verifying PDC system with tests"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py"
}
Now let me look at the combat system, ship class definitions with firing arcs, and the hardpoint system.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/hardpoint.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/ship_classes/corvette.json"
}
Now let me check how weapon mounts are stored on ships and how they could be used for firing arc enforcement.

🔧 Tool: Grep
Input: {
  "pattern": "weapon_mounts",
  "glob": "**/*.py",
  "output_mode": "content",
  "-n": true
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/projectile_manager.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/tests/systems/combat/test_combat_system.py"
}
Now let me check how ship weapon_mounts are stored and accessible in the combat system, and look at the ship.py to understand how weapon_mounts get passed to the combat system.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/ship.py",
  "offset": 30,
  "limit": 60
}
Good. I can see that `weapon_mounts` data is stored on ships from the ship class JSON definitions. Now I need to implement the three remaining features: firing arc enforcement, burst fire, and armor penetration. Let me implement them.

Let me start with firing arc enforcement in `truth_weapons.py`. The weapon needs access to the ship's weapon_mounts data to know its arc limits.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "offset": 99,
  "limit": 30
}
Now I have a clear picture. I need to:

1. **Firing arc enforcement**: The TruthWeapon needs to know its firing arc limits. The cleanest way is to store firing arc data on the weapon itself (set during combat system initialization from ship's `weapon_mounts`), then check it during `calculate_solution`.

2. **Burst fire**: Modify `fire()` to fire a burst of rounds for PDC-type weapons.

3. **Armor penetration**: Use the target ship's armor data and the weapon's `armor_penetration` to modify effective damage.

Let me implement all three.

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "class TruthWeapon:\n    \"\"\"Physics-based weapon with realistic ballistics and engagement.\"\"\"\n\n    def __init__(self, specs: WeaponSpecs, mount_id: str = \"default\"):\n        \"\"\"Initialize weapon with specifications.\n\n        Args:\n            specs: Weapon physical specifications\n            mount_id: Unique identifier for this weapon mount\n        \"\"\"\n        self.specs = specs\n        self.mount_id = mount_id\n\n        # State\n        self.enabled = True\n        self.ammo = specs.ammo_capacity\n        self.heat = 0.0\n        self.max_heat = 100.0\n\n        # Timing\n        self.last_fired = -specs.cycle_time  # Ready to fire immediately\n        self.charge_start = None\n        self.charging = False\n\n        # Reload state (magazine-based for PDCs, per-round for railguns)\n        self.reloading = False\n        self.reload_progress = 0.0  # 0.0 to 1.0\n        self._reload_timer = 0.0\n        # PDC magazine: reload triggers every N rounds\n        self._magazine_size = 200 if specs.reload_time > 0 else 0\n        self._rounds_since_reload = 0\n\n        # Tracking\n        self.current_solution: Optional[FiringSolution] = None\n        self.turret_bearing = {\"pitch\": 0.0, \"yaw\": 0.0}\n        self.target_bearing = {\"pitch\": 0.0, \"yaw\": 0.0}\n\n        # Events\n        self.event_bus = EventBus.get_instance()",
  "new_string": "class TruthWeapon:\n    \"\"\"Physics-based weapon with realistic ballistics and engagement.\"\"\"\n\n    def __init__(self, specs: WeaponSpecs, mount_id: str = \"default\"):\n        \"\"\"Initialize weapon with specifications.\n\n        Args:\n            specs: Weapon physical specifications\n            mount_id: Unique identifier for this weapon mount\n        \"\"\"\n        self.specs = specs\n        self.mount_id = mount_id\n\n        # State\n        self.enabled = True\n        self.ammo = specs.ammo_capacity\n        self.heat = 0.0\n        self.max_heat = 100.0\n\n        # Timing\n        self.last_fired = -specs.cycle_time  # Ready to fire immediately\n        self.charge_start = None\n        self.charging = False\n\n        # Reload state (magazine-based for PDCs, per-round for railguns)\n        self.reloading = False\n        self.reload_progress = 0.0  # 0.0 to 1.0\n        self._reload_timer = 0.0\n        # PDC magazine: reload triggers every N rounds\n        self._magazine_size = 200 if specs.reload_time > 0 else 0\n        self._rounds_since_reload = 0\n\n        # Firing arc constraints (set from ship_class weapon_mounts config)\n        self.firing_arc: Optional[Dict[str, float]] = None  # {azimuth_min, azimuth_max, elevation_min, elevation_max}\n\n        # Tracking\n        self.current_solution: Optional[FiringSolution] = None\n        self.turret_bearing = {\"pitch\": 0.0, \"yaw\": 0.0}\n        self.target_bearing = {\"pitch\": 0.0, \"yaw\": 0.0}\n\n        # Events\n        self.event_bus = EventBus.get_instance()"
}
Now replace the `solution.in_arc = True  # TODO: implement firing arcs` line with actual firing arc enforcement:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "        solution.tracking = turret_error < 5.0  # Within 5 degrees\n        solution.in_arc = True  # TODO: implement firing arcs",
  "new_string": "        solution.tracking = turret_error < 5.0  # Within 5 degrees\n\n        # Check firing arc constraints from weapon mount config\n        if self.firing_arc:\n            az_min = self.firing_arc.get(\"azimuth_min\", -180)\n            az_max = self.firing_arc.get(\"azimuth_max\", 180)\n            el_min = self.firing_arc.get(\"elevation_min\", -90)\n            el_max = self.firing_arc.get(\"elevation_max\", 90)\n            yaw = solution.lead_angle[\"yaw\"]\n            pitch = solution.lead_angle[\"pitch\"]\n            # Normalize yaw to [-180, 180] for comparison\n            while yaw > 180:\n                yaw -= 360\n            while yaw < -180:\n                yaw += 360\n            solution.in_arc = (az_min <= yaw <= az_max) and (el_min <= pitch <= el_max)\n        else:\n            solution.in_arc = True  # No arc constraints defined"
}
Now add a reason string for arc check failure:

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 410,
  "limit": 40
}
I need to add the "out of arc" reason to the not-ready reasons:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "            elif not solution.in_range:\n                if solution.range_to_target < self.specs.min_range:\n                    solution.reason = f\"Target too close ({solution.range_to_target:.0f}m < {self.specs.min_range:.0f}m)\"\n                else:\n                    solution.reason = f\"Target out of range ({solution.range_to_target:.0f}m > {self.specs.effective_range:.0f}m)\"\n            elif not solution.tracking:",
  "new_string": "            elif not solution.in_range:\n                if solution.range_to_target < self.specs.min_range:\n                    solution.reason = f\"Target too close ({solution.range_to_target:.0f}m < {self.specs.min_range:.0f}m)\"\n                else:\n                    solution.reason = f\"Target out of range ({solution.range_to_target:.0f}m > {self.specs.effective_range:.0f}m)\"\n            elif not solution.in_arc:\n                solution.reason = \"Target outside firing arc\"\n            elif not solution.tracking:"
}
Now I need to wire up the firing arc data from `weapon_mounts` to the TruthWeapon instances. This happens in the CombatSystem when it creates weapons. Let me update the combat system to pass firing arc data:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "old_string": "        # Initialize truth weapons\n        self.truth_weapons: Dict[str, TruthWeapon] = {}\n\n        # Create railguns\n        num_railguns = config.get(\"railguns\", config.get(\"railgun_mounts\", 1))\n        for i in range(num_railguns):\n            mount_id = f\"railgun_{i+1}\"\n            self.truth_weapons[mount_id] = create_railgun(mount_id)\n\n        # Create PDCs\n        num_pdcs = config.get(\"pdcs\", config.get(\"pdc_turrets\", 2))\n        for i in range(num_pdcs):\n            mount_id = f\"pdc_{i+1}\"\n            self.truth_weapons[mount_id] = create_pdc(mount_id)",
  "new_string": "        # Initialize truth weapons\n        self.truth_weapons: Dict[str, TruthWeapon] = {}\n\n        # Build firing arc lookup from weapon_mounts config\n        arc_lookup: Dict[str, dict] = {}\n        for mount in config.get(\"weapon_mounts\", []):\n            mid = mount.get(\"mount_id\", \"\")\n            if \"firing_arc\" in mount:\n                arc_lookup[mid] = mount[\"firing_arc\"]\n\n        # Create railguns\n        num_railguns = config.get(\"railguns\", config.get(\"railgun_mounts\", 1))\n        for i in range(num_railguns):\n            mount_id = f\"railgun_{i+1}\"\n            weapon = create_railgun(mount_id)\n            weapon.firing_arc = arc_lookup.get(mount_id)\n            self.truth_weapons[mount_id] = weapon\n\n        # Create PDCs\n        num_pdcs = config.get(\"pdcs\", config.get(\"pdc_turrets\", 2))\n        for i in range(num_pdcs):\n            mount_id = f\"pdc_{i+1}\"\n            weapon = create_pdc(mount_id)\n            weapon.firing_arc = arc_lookup.get(mount_id)\n            self.truth_weapons[mount_id] = weapon"
}
Now I need to make sure the weapon_mounts data actually reaches the combat system config. Let me check how the combat system gets initialized from ship config.

🔧 Tool: Grep
Input: {
  "pattern": "combat.*CombatSystem|systems\\[.combat.\\]|\\\"combat\\\".*config",
  "path": "/projects/spaceship-sim/hybrid/ship.py",
  "output_mode": "content",
  "-n": true
}

🔧 Tool: Grep
Input: {
  "pattern": "CombatSystem|combat_system",
  "path": "/projects/spaceship-sim/hybrid/ship.py",
  "output_mode": "content",
  "-n": true
}

🔧 Tool: Grep
Input: {
  "pattern": "combat",
  "path": "/projects/spaceship-sim/hybrid/ship.py",
  "output_mode": "content",
  "-n": true
}
Let me look at how systems are registered/initialized from config.

🔧 Tool: Grep
Input: {
  "pattern": "_init_systems|_register_system|system_registry|SYSTEM_REGISTRY",
  "path": "/projects/spaceship-sim/hybrid",
  "output_mode": "content",
  "-n": true
}

🔧 Tool: Grep
Input: {
  "pattern": "def.*systems|self\\.systems\\[|self\\.systems =",
  "path": "/projects/spaceship-sim/hybrid/ship.py",
  "output_mode": "content",
  "-n": true
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/ship.py",
  "offset": 195,
  "limit": 55
}
I see - the combat system receives its config from `systems_config["combat"]`. The weapon_mounts are stored at the top level of the ship config, not inside the combat config. I need to pass the weapon_mounts data into the combat config. Let me check where `_load_systems` is called from and how the config flows.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/ship.py",
  "offset": 110,
  "limit": 25
}
The config at `systems_config["combat"]` is only the combat-specific config (e.g. `{"enabled": true, "railguns": 1, "pdcs": 2}`). The `weapon_mounts` are a top-level key in the ship config. I need to inject weapon_mounts into the combat config before the CombatSystem is created. The cleanest way is to do this in `_load_systems`:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/ship.py",
  "old_string": "    def _load_systems(self, systems_config):\n        \"\"\"\n        Load ship systems from configuration\n        \n        Args:\n            systems_config (dict): Dictionary of system configurations\n        \"\"\"\n        from hybrid.systems import get_system_class\n        \n        # Ensure essential systems are always present with defaults\n        # These systems are required for Expanse-style flight model\n        essential_systems = {\n            \"helm\": {},      # Helm for manual control interface\n            \"rcs\": {},       # RCS for attitude control (torque-based rotation)\n            \"flight_computer\": {},  # Flight computer for high-level manoeuvre commands\n            \"ops\": {},       # Ops for power allocation and damage control\n        }\n        \n        # Merge config with defaults (config takes precedence)\n        merged_config = {**essential_systems, **systems_config}\n        \n        # Load each system type\n        for system_type, config in merged_config.items():",
  "new_string": "    def _load_systems(self, systems_config):\n        \"\"\"\n        Load ship systems from configuration\n\n        Args:\n            systems_config (dict): Dictionary of system configurations\n        \"\"\"\n        from hybrid.systems import get_system_class\n\n        # Ensure essential systems are always present with defaults\n        # These systems are required for Expanse-style flight model\n        essential_systems = {\n            \"helm\": {},      # Helm for manual control interface\n            \"rcs\": {},       # RCS for attitude control (torque-based rotation)\n            \"flight_computer\": {},  # Flight computer for high-level manoeuvre commands\n            \"ops\": {},       # Ops for power allocation and damage control\n        }\n\n        # Merge config with defaults (config takes precedence)\n        merged_config = {**essential_systems, **systems_config}\n\n        # Inject weapon_mounts into combat config for firing arc enforcement\n        if \"combat\" in merged_config and self.weapon_mounts:\n            combat_cfg = merged_config[\"combat\"]\n            if isinstance(combat_cfg, dict) and \"weapon_mounts\" not in combat_cfg:\n                combat_cfg[\"weapon_mounts\"] = self.weapon_mounts\n\n        # Load each system type\n        for system_type, config in merged_config.items():"
}
Good, firing arc enforcement is now complete. Let me update the todo and move to burst fire.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "in_progress",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "pending",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Verify PDC system works correctly with tests",
      "status": "pending",
      "activeForm": "Verifying PDC system with tests"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}
Now let me implement burst fire. The `fire()` method should fire `burst_count` rounds when burst_count > 1 (PDC fires 5-round bursts). Each round gets its own hit roll and damage application. Let me re-read the fire method to plan the change.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 453,
  "limit": 150
}
Now I'll rewrite the fire method to support burst fire. For burst weapons (burst_count > 1), each round in the burst gets its own hit roll, its own ammo consumption, its own heat, and its own subsystem target. The return value aggregates the burst results.

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "        # Fire!\n        self.last_fired = sim_time\n        if self.ammo is not None:\n            self.ammo -= 1\n\n        # Magazine reload: PDC-style weapons trigger reload after N rounds\n        if self._magazine_size > 0 and self.ammo is not None and self.ammo > 0:\n            self._rounds_since_reload += 1\n            if self._rounds_since_reload >= self._magazine_size:\n                self.reloading = True\n                self._reload_timer = self.specs.reload_time\n                self.reload_progress = 0.0\n                self.event_bus.publish(\"weapon_reloading\", {\n                    \"weapon\": self.specs.name,\n                    \"mount_id\": self.mount_id,\n                    \"reload_time\": self.specs.reload_time,\n                })\n\n        self.heat += 10.0 * (1.0 / max(0.5, damage_factor))\n        if damage_model is not None:\n            heat_scale = self.specs.subsystem_damage / max(1.0, self.specs.base_damage)\n            heat_amount = self.specs.power_per_shot * (1.0 + heat_scale)\n            if heat_amount > 0:\n                damage_model.add_heat(\"weapons\", heat_amount, event_bus, ship_id)\n\n        # Determine hit\n        import random\n        hit_roll = random.random()\n        hit = hit_roll < self.current_solution.hit_probability\n\n        # Calculate damage\n        damage_result = None\n        effective_damage = 0.0\n\n        if hit and target_ship:\n            # Apply damage\n            effective_damage = self.specs.base_damage * damage_factor\n            subsystem_damage = self.specs.subsystem_damage * damage_factor\n\n            subsystem_target = target_subsystem or self._select_subsystem_target()\n\n            # Apply to target\n            if hasattr(target_ship, 'take_damage'):\n                damage_result = target_ship.take_damage(\n                    effective_damage,\n                    source=f\"{ship_id}:{self.specs.name}\",\n                    target_subsystem=subsystem_target,\n                )\n\n            # Apply subsystem damage\n            if hasattr(target_ship, 'damage_model'):\n                target_ship.damage_model.apply_damage(\n                    subsystem_target, subsystem_damage\n                )\n                if damage_result:\n                    damage_result[\"subsystem_hit\"] = subsystem_target\n                    damage_result[\"subsystem_damage\"] = subsystem_damage\n\n        # Publish event\n        target_id = getattr(target_ship, 'id', None) if target_ship else None\n        self.event_bus.publish(\"weapon_fired\", {\n            \"weapon\": self.specs.name,\n            \"mount_id\": self.mount_id,\n            \"ship_id\": ship_id,\n            \"target\": target_id,\n            \"hit\": hit,\n            \"hit_probability\": self.current_solution.hit_probability,\n            \"range\": self.current_solution.range_to_target,\n            \"damage\": effective_damage if hit else 0,\n            \"damage_result\": damage_result,\n        })\n\n        return {\n            \"ok\": True,\n            \"hit\": hit,\n            \"damage\": effective_damage if hit else 0,\n            \"target\": target_id,\n            \"range\": self.current_solution.range_to_target,\n            \"time_of_flight\": self.current_solution.time_of_flight,\n            \"hit_probability\": self.current_solution.hit_probability,\n            \"ammo_remaining\": self.ammo,\n            \"heat\": self.heat,\n            \"damage_result\": damage_result,\n        }",
  "new_string": "        # Fire burst (1 round for railgun, burst_count for PDC)\n        import random\n\n        self.last_fired = sim_time\n        target_id = getattr(target_ship, 'id', None) if target_ship else None\n\n        # Armor penetration: compare weapon penetration vs target armor\n        armor_factor = 1.0\n        if target_ship and hasattr(target_ship, 'armor') and target_ship.armor:\n            armor_factor = self._calculate_armor_factor(target_ship.armor)\n\n        burst_hits = 0\n        burst_damage = 0.0\n        burst_rounds = 0\n        burst_results = []\n\n        for shot_i in range(self.specs.burst_count):\n            # Check ammo for each shot in burst\n            if self.ammo is not None and self.ammo <= 0:\n                break\n\n            # Consume ammo\n            if self.ammo is not None:\n                self.ammo -= 1\n            burst_rounds += 1\n\n            # Magazine reload check per round\n            if self._magazine_size > 0 and self.ammo is not None and self.ammo > 0:\n                self._rounds_since_reload += 1\n                if self._rounds_since_reload >= self._magazine_size:\n                    self.reloading = True\n                    self._reload_timer = self.specs.reload_time\n                    self.reload_progress = 0.0\n                    self.event_bus.publish(\"weapon_reloading\", {\n                        \"weapon\": self.specs.name,\n                        \"mount_id\": self.mount_id,\n                        \"reload_time\": self.specs.reload_time,\n                    })\n                    break  # Stop burst on reload\n\n            # Heat per round\n            self.heat += 10.0 * (1.0 / max(0.5, damage_factor))\n            if damage_model is not None:\n                heat_scale = self.specs.subsystem_damage / max(1.0, self.specs.base_damage)\n                heat_amount = self.specs.power_per_shot * (1.0 + heat_scale)\n                if heat_amount > 0:\n                    damage_model.add_heat(\"weapons\", heat_amount, event_bus, ship_id)\n\n            # Hit roll per round\n            hit = random.random() < self.current_solution.hit_probability\n\n            shot_damage = 0.0\n            damage_result = None\n\n            if hit and target_ship:\n                effective_damage = self.specs.base_damage * damage_factor * armor_factor\n                subsystem_dmg = self.specs.subsystem_damage * damage_factor * armor_factor\n                subsystem_target = target_subsystem or self._select_subsystem_target()\n\n                if hasattr(target_ship, 'take_damage'):\n                    damage_result = target_ship.take_damage(\n                        effective_damage,\n                        source=f\"{ship_id}:{self.specs.name}\",\n                        target_subsystem=subsystem_target,\n                    )\n\n                if hasattr(target_ship, 'damage_model'):\n                    target_ship.damage_model.apply_damage(\n                        subsystem_target, subsystem_dmg\n                    )\n                    if damage_result:\n                        damage_result[\"subsystem_hit\"] = subsystem_target\n                        damage_result[\"subsystem_damage\"] = subsystem_dmg\n\n                shot_damage = effective_damage\n                burst_hits += 1\n                burst_damage += shot_damage\n\n            burst_results.append({\n                \"hit\": hit,\n                \"damage\": shot_damage,\n                \"damage_result\": damage_result,\n            })\n\n            # Stop burst if overheating\n            if self.heat >= self.max_heat * 0.95:\n                break\n\n        # Publish single event summarizing the burst\n        self.event_bus.publish(\"weapon_fired\", {\n            \"weapon\": self.specs.name,\n            \"mount_id\": self.mount_id,\n            \"ship_id\": ship_id,\n            \"target\": target_id,\n            \"hit\": burst_hits > 0,\n            \"hits\": burst_hits,\n            \"rounds_fired\": burst_rounds,\n            \"hit_probability\": self.current_solution.hit_probability,\n            \"range\": self.current_solution.range_to_target,\n            \"damage\": burst_damage,\n        })\n\n        return {\n            \"ok\": True,\n            \"hit\": burst_hits > 0,\n            \"hits\": burst_hits,\n            \"rounds_fired\": burst_rounds,\n            \"damage\": burst_damage,\n            \"target\": target_id,\n            \"range\": self.current_solution.range_to_target,\n            \"time_of_flight\": self.current_solution.time_of_flight,\n            \"hit_probability\": self.current_solution.hit_probability,\n            \"ammo_remaining\": self.ammo,\n            \"heat\": self.heat,\n            \"burst_results\": burst_results,\n        }"
}
Now I need to add the `_calculate_armor_factor` method. Let me add it right after `_select_subsystem_target`:

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 620,
  "limit": 50
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 670,
  "limit": 40
}
Now add the `_calculate_armor_factor` method after `_select_subsystem_target`:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "        return \"weapons\"  # fallback\n\n    def get_ammo_mass(self) -> float:",
  "new_string": "        return \"weapons\"  # fallback\n\n    def _calculate_armor_factor(self, armor: Dict) -> float:\n        \"\"\"Calculate damage multiplier based on armor vs weapon penetration.\n\n        Armor sections have thickness_cm. Thicker armor reduces damage\n        more, but high armor_penetration weapons bypass it.\n\n        PDC (0.5 pen) vs 3cm armor → ~0.5x damage (struggles)\n        Railgun (1.5 pen) vs 3cm armor → ~1.0x damage (punches through)\n\n        Args:\n            armor: Ship armor dict with sections {fore, aft, ...} each\n                having thickness_cm.\n\n        Returns:\n            float: Damage multiplier (0.2 to 1.0).\n        \"\"\"\n        # Average armor thickness across all sections\n        thicknesses = []\n        for section_data in armor.values():\n            if isinstance(section_data, dict):\n                thicknesses.append(section_data.get(\"thickness_cm\", 0.0))\n        if not thicknesses:\n            return 1.0\n\n        avg_thickness = sum(thicknesses) / len(thicknesses)\n        # Armor resistance scales with thickness: 1cm = 0.1 resistance\n        armor_resistance = avg_thickness * 0.1\n        # Effective factor: penetration / (penetration + resistance)\n        pen = self.specs.armor_penetration\n        factor = pen / (pen + armor_resistance)\n        return max(0.2, min(1.0, factor))\n\n    def get_ammo_mass(self) -> float:"
}
Now I also need to update the `CombatSystem.fire_weapon` method since the return dict from `fire()` now uses `hits` and `rounds_fired` instead of just `hit`. Let me check how the hits counter works:

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "offset": 163,
  "limit": 25
}
I need to update the combat system to properly count burst rounds. The `shots_fired` should count rounds, not trigger pulls:

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "old_string": "        if result.get(\"ok\"):\n            self.shots_fired += 1\n            if result.get(\"hit\"):\n                self.hits += 1\n                self.damage_dealt += result.get(\"damage\", 0)\n            self.engaging = True",
  "new_string": "        if result.get(\"ok\"):\n            rounds = result.get(\"rounds_fired\", 1)\n            self.shots_fired += rounds\n            hits = result.get(\"hits\", 1 if result.get(\"hit\") else 0)\n            self.hits += hits\n            self.damage_dealt += result.get(\"damage\", 0)\n            self.engaging = True"
}
Now let me update the todos and run the tests to verify everything works.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "completed",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "completed",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Verify PDC system works correctly with tests",
      "status": "in_progress",
      "activeForm": "Verifying PDC system with tests"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}

🔧 Tool: Bash
Input: {
  "command": ".venv/bin/python -m pytest tests/systems/combat/test_combat_system.py -v 2>&1",
  "description": "Run combat system tests",
  "timeout": 30000
}

🔧 Tool: Bash
Input: {
  "command": "which python3 && python3 -m pytest tests/systems/combat/test_combat_system.py -v 2>&1",
  "description": "Find python and run combat tests",
  "timeout": 30000
}

🔧 Tool: Bash
Input: {
  "command": "ls /projects/spaceship-sim/.venv/bin/python* 2>/dev/null; ls /usr/bin/python* 2>/dev/null; which python 2>/dev/null; which python3.12 2>/dev/null",
  "description": "Find available Python binaries"
}

🔧 Tool: Bash
Input: {
  "command": ".venv/bin/python -m pytest tests/systems/combat/test_combat_system.py -v 2>&1",
  "description": "Run combat system tests from project root",
  "timeout": 30000
}

🔧 Tool: Bash
Input: {
  "command": "/projects/spaceship-sim/.venv/bin/python -m pytest tests/systems/combat/test_combat_system.py -v 2>&1",
  "description": "Run combat tests with absolute path",
  "timeout": 30000
}

🔧 Tool: Bash
Input: {
  "command": "file /projects/spaceship-sim/.venv/bin/python3",
  "description": "Check if python3 exists in venv"
}

🔧 Tool: Bash
Input: {
  "command": "ls -la /projects/spaceship-sim/.venv/bin/python3 2>&1 && /projects/spaceship-sim/.venv/bin/python3 --version 2>&1",
  "description": "Check python3 symlink and version"
}

🔧 Tool: Bash
Input: {
  "command": "ls /usr/bin/python* 2>&1; ls /usr/local/bin/python* 2>&1",
  "description": "Find python binary locations"
}
Python isn't available in this environment. My memory notes mention this: "Python may not be directly available in CI/test envs". Let me verify the code is syntactically correct by doing a careful review instead.

🔧 Tool: Task
Input: {
  "description": "Verify PDC code correctness",
  "prompt": "Review the following files for syntax errors, logic bugs, and integration issues. Do NOT modify the files, just report any issues found:\n\n1. /projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py - Check the entire file, especially:\n   - The firing_arc attribute initialization\n   - The firing arc check in calculate_solution (around line 392-410)\n   - The burst fire loop in fire() method (around line 519-634)\n   - The _calculate_armor_factor method (around line 675)\n   \n2. /projects/spaceship-sim/hybrid/systems/combat/combat_system.py - Check:\n   - The arc_lookup construction from weapon_mounts config\n   - The updated shots_fired/hits counting with rounds_fired\n\n3. /projects/spaceship-sim/hybrid/ship.py - Check:\n   - The weapon_mounts injection into combat config (the new code around line 218-221)\n\nReport any problems: missing imports, undefined variables, wrong method signatures, logic errors, etc.",
  "subagent_type": "qa-tester"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py"
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/ship.py"
}

🔧 Tool: Grep
Input: {
  "pattern": "ship_class_registry",
  "output_mode": "files_with_matches"
}

🔧 Tool: Grep
Input: {
  "pattern": "resolve_ship_config",
  "output_mode": "files_with_matches"
}

🔧 Tool: Bash
Input: {
  "command": "python3 -m py_compile hybrid/systems/weapons/truth_weapons.py",
  "description": "Check truth_weapons.py for syntax errors"
}

🔧 Tool: Bash
Input: {
  "command": "python3 -m py_compile hybrid/systems/combat/combat_system.py",
  "description": "Check combat_system.py for syntax errors"
}

🔧 Tool: Bash
Input: {
  "command": "python3 -m py_compile hybrid/ship.py",
  "description": "Check ship.py for syntax errors"
}

🔧 Tool: Bash
Input: {
  "command": "/projects/spaceship-sim/.venv/bin/python -m py_compile /projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "description": "Check truth_weapons.py for syntax errors using venv python"
}

🔧 Tool: Bash
Input: {
  "command": "/projects/spaceship-sim/.venv/bin/python -m py_compile /projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "description": "Check combat_system.py for syntax errors using venv python"
}

🔧 Tool: Bash
Input: {
  "command": "/projects/spaceship-sim/.venv/bin/python -m py_compile /projects/spaceship-sim/hybrid/ship.py",
  "description": "Check ship.py for syntax errors using venv python"
}

🔧 Tool: Bash
Input: {
  "command": "which python || which python3.12 || ls -la /usr/bin/python*",
  "description": "Find available Python interpreter"
}


Good review. Let me fix the identified issues before declaring this complete.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "completed",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "completed",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Fix firing arc boundary crossing logic",
      "status": "in_progress",
      "activeForm": "Fixing firing arc boundary crossing logic"
    },
    {
      "content": "Fix magazine reload on last round edge case",
      "status": "pending",
      "activeForm": "Fixing magazine reload edge case"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}
**Fix 1: Firing arc boundary crossing** - Handle arcs that span the -180/+180 wrap (e.g., rear-facing turrets):

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 393,
  "limit": 20
}

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "        # Check firing arc constraints from weapon mount config\n        if self.firing_arc:\n            az_min = self.firing_arc.get(\"azimuth_min\", -180)\n            az_max = self.firing_arc.get(\"azimuth_max\", 180)\n            el_min = self.firing_arc.get(\"elevation_min\", -90)\n            el_max = self.firing_arc.get(\"elevation_max\", 90)\n            yaw = solution.lead_angle[\"yaw\"]\n            pitch = solution.lead_angle[\"pitch\"]\n            # Normalize yaw to [-180, 180] for comparison\n            while yaw > 180:\n                yaw -= 360\n            while yaw < -180:\n                yaw += 360\n            solution.in_arc = (az_min <= yaw <= az_max) and (el_min <= pitch <= el_max)\n        else:\n            solution.in_arc = True  # No arc constraints defined",
  "new_string": "        # Check firing arc constraints from weapon mount config\n        if self.firing_arc:\n            az_min = self.firing_arc.get(\"azimuth_min\", -180)\n            az_max = self.firing_arc.get(\"azimuth_max\", 180)\n            el_min = self.firing_arc.get(\"elevation_min\", -90)\n            el_max = self.firing_arc.get(\"elevation_max\", 90)\n            yaw = solution.lead_angle[\"yaw\"]\n            pitch = solution.lead_angle[\"pitch\"]\n            # Normalize yaw to [-180, 180] for comparison\n            while yaw > 180:\n                yaw -= 360\n            while yaw < -180:\n                yaw += 360\n            # Azimuth check handles arcs that wrap past +/-180\n            # (e.g. rear-facing arc: az_min=170, az_max=-170)\n            if az_min <= az_max:\n                az_ok = az_min <= yaw <= az_max\n            else:\n                # Wrapping arc: valid if yaw >= min OR yaw <= max\n                az_ok = yaw >= az_min or yaw <= az_max\n            el_ok = el_min <= pitch <= el_max\n            solution.in_arc = az_ok and el_ok\n        else:\n            solution.in_arc = True  # No arc constraints defined"
}
**Fix 2: Magazine reload on last round** - The reload should trigger even when ammo reaches 0:

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 540,
  "limit": 25
}

🔧 Tool: Edit
Input: {
  "replace_all": false,
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "old_string": "            # Magazine reload check per round\n            if self._magazine_size > 0 and self.ammo is not None and self.ammo > 0:\n                self._rounds_since_reload += 1\n                if self._rounds_since_reload >= self._magazine_size:",
  "new_string": "            # Magazine reload check per round (>= 0 so reload triggers on last round too)\n            if self._magazine_size > 0 and self.ammo is not None and self.ammo >= 0:\n                self._rounds_since_reload += 1\n                if self._rounds_since_reload >= self._magazine_size:"
}

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "completed",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "completed",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Fix firing arc boundary crossing logic",
      "status": "completed",
      "activeForm": "Fixing firing arc boundary crossing logic"
    },
    {
      "content": "Fix magazine reload on last round edge case",
      "status": "completed",
      "activeForm": "Fixing magazine reload edge case"
    },
    {
      "content": "Final code review",
      "status": "in_progress",
      "activeForm": "Doing final code review"
    },
    {
      "content": "Output final summary",
      "status": "pending",
      "activeForm": "Outputting final summary"
    }
  ]
}
Let me do a final review of all three modified files to make sure everything is consistent.

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 140,
  "limit": 40
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/combat/combat_system.py",
  "offset": 40,
  "limit": 30
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/ship.py",
  "offset": 214,
  "limit": 12
}
Everything looks correct. Let me verify the full fire method and the armor factor method one more time:

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 520,
  "limit": 130
}

🔧 Tool: Read
Input: {
  "file_path": "/projects/spaceship-sim/hybrid/systems/weapons/truth_weapons.py",
  "offset": 680,
  "limit": 40
}
Everything looks good. Let me verify the math on the armor factor to make sure it matches the design intent:

- PDC (0.5 pen) vs corvette (avg ~2.1cm armor): resistance = 0.21, factor = 0.5 / (0.5 + 0.21) = 0.70 — PDC does 70% damage, reduced but still effective at close range
- Railgun (1.5 pen) vs corvette: factor = 1.5 / (1.5 + 0.21) = 0.88 — railgun barely affected by light armor
- PDC vs destroyer heavy armor (say 5cm): factor = 0.5 / (0.5 + 0.5) = 0.50 — struggles significantly

That's reasonable. Let me finalize.

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "completed",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "completed",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Fix firing arc boundary crossing logic",
      "status": "completed",
      "activeForm": "Fixing firing arc boundary crossing logic"
    },
    {
      "content": "Fix magazine reload on last round edge case",
      "status": "completed",
      "activeForm": "Fixing magazine reload edge case"
    },
    {
      "content": "Final code review",
      "status": "completed",
      "activeForm": "Doing final code review"
    },
    {
      "content": "Output final summary",
      "status": "in_progress",
      "activeForm": "Outputting final summary"
    }
  ]
}
<summary>
## Summary: Point Defense Cannon System (Narwhal-III)

### Changes Implemented

**From previous implementation (already complete):**
- PDC weapon specs defined (Narwhal-III: 3 km/s muzzle velocity, 5km range, 5-round bursts, 2000 ammo, 10 rounds/sec, 50g rounds)
- TruthWeapon class with physics-based ballistics, lead prediction, hit probability
- CombatSystem integration with `create_pdc()` factory, multi-mount support
- Targeting pipeline integration (lock → track → fire solution)
- Projectile manager for in-flight ballistics tracking
- Magazine reload system (200 rounds per magazine, 3s reload)
- Ammunition mass tracking (dynamic ship mass via F=ma)
- Subsystem damage targeting (PDC fragmentation weights: sensors 30%, RCS 25%, weapons 20%)
- Combat logging with causal chain feedback
- Event bus integration (weapon_fired, weapon_reloading, weapon_reloaded)
- GUI components (weapons-status.js, weapon-controls.js, combat-log.js)
- Station permissions (TACTICAL station has fire_pdc, fire_all, etc.)
- Ship class definitions with PDC hardpoints and firing arcs (corvette.json etc.)
- Tests for PDC specs, creation, combat system integration

**New in this session (completing the feature):**
- **Firing arc enforcement**: TruthWeapon now checks `firing_arc` constraints (azimuth + elevation limits) during `calculate_solution()`. Handles wrap-around arcs that span the -180/+180 boundary. Ships with `weapon_mounts` config automatically have arcs enforced per-turret.
- **Burst fire**: PDC `fire()` now fires `burst_count` rounds (5 for PDC, 1 for railgun) per trigger pull. Each round gets its own hit roll, subsystem target, and damage application. Burst stops early on reload trigger, ammo depletion, or overheating.
- **Armor penetration**: Damage is now modulated by target ship armor vs weapon `armor_penetration`. Uses formula `pen / (pen + resistance)` where resistance = avg_thickness * 0.1. PDC (0.5 pen) struggles vs armor; railgun (1.5 pen) punches through.
- **Bug fix**: Magazine reload now triggers correctly when ammo reaches 0 (was checking `ammo > 0`, now `ammo >= 0`)
- **Data flow**: Ship `weapon_mounts` are injected into combat system config during `_load_systems()` so firing arcs reach individual weapon instances

### Files Modified
- `hybrid/systems/weapons/truth_weapons.py` — Added `firing_arc` attribute, arc enforcement in `calculate_solution()`, burst fire loop in `fire()`, `_calculate_armor_factor()` method, fixed magazine reload edge case
- `hybrid/systems/combat/combat_system.py` — Added `arc_lookup` construction from `weapon_mounts` config, applies firing arc to each weapon instance, updated `shots_fired`/`hits` counters for burst fire
- `hybrid/ship.py` — Injects `weapon_mounts` into combat system config during `_load_systems()`

### Notes for Developer
- Python is not available in this environment, so tests could not be run. Manual code review was performed instead.
- The firing arc check uses the `lead_angle` (yaw/pitch) from the firing solution, which is in world-frame relative to the shooter. For ships that rotate, you may want to transform this into ship-local coordinates in a future iteration.
- Armor factor currently uses average thickness across all sections. A future enhancement could use the specific section facing the attacker based on relative geometry.
- Railgun burst_count is 1, so it continues to fire single shots — the burst loop is a no-op for single-shot weapons.
</summary>

🔧 Tool: TodoWrite
Input: {
  "todos": [
    {
      "content": "Review existing PDC implementation state",
      "status": "completed",
      "activeForm": "Reviewing existing PDC implementation"
    },
    {
      "content": "Implement firing arc constraint enforcement",
      "status": "completed",
      "activeForm": "Implementing firing arc constraint enforcement"
    },
    {
      "content": "Implement burst fire for PDC",
      "status": "completed",
      "activeForm": "Implementing burst fire for PDC"
    },
    {
      "content": "Implement armor penetration interaction",
      "status": "completed",
      "activeForm": "Implementing armor penetration interaction"
    },
    {
      "content": "Fix firing arc boundary crossing logic",
      "status": "completed",
      "activeForm": "Fixing firing arc boundary crossing logic"
    },
    {
      "content": "Fix magazine reload on last round edge case",
      "status": "completed",
      "activeForm": "Fixing magazine reload edge case"
    },
    {
      "content": "Final code review",
      "status": "completed",
      "activeForm": "Doing final code review"
    },
    {
      "content": "Output final summary",
      "status": "completed",
      "activeForm": "Outputting final summary"
    }
  ]
}
The PDC system feature is now complete. The three remaining gaps from the previous implementation have been filled:

1. **Firing arcs** — turrets now enforce azimuth/elevation constraints from ship class config, with proper wrap-around handling
2. **Burst fire** — PDC fires 5-round bursts per trigger pull with independent hit rolls per round
3. **Armor penetration** — damage is reduced by target armor, with PDC struggling against heavy armor while railgun punches through