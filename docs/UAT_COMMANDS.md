# UAT Commands

Use this file when you just need the exact commands without reading the full runbook.

## Standard UAT Sequence

### 1. Start the default Svelte stack

```bash
python3 tools/start_gui_stack.py --browser --rcon-password 'replace-this'
```

### 2. Run the fast bridge smoke

```bash
python3 tools/check_station_wiring.py
```

Expected result:
- `PASS loadout`
- `PASS manual`
- `PASS auto`
- `PASS overall`

### 3. Run the live log monitor in a second terminal

```bash
python3 tools/uat_monitor.py --follow --fail-on-critical
```

## Helper Script

If you do not want to retype the commands, use:

```bash
tools/uat_commands.sh
```

Supported modes:

```bash
tools/uat_commands.sh print
tools/uat_commands.sh start 'replace-this'
tools/uat_commands.sh smoke
tools/uat_commands.sh monitor
```

## Related Docs

- [UAT_MASTER_PLAN.md](/home/flax/games/spaceship-sim/docs/UAT_MASTER_PLAN.md)
- [STATION_UAT_WIRING_CHECKLIST.md](/home/flax/games/spaceship-sim/docs/STATION_UAT_WIRING_CHECKLIST.md)
- [MOBILE_GUI_TESTING.md](/home/flax/games/spaceship-sim/docs/MOBILE_GUI_TESTING.md)
