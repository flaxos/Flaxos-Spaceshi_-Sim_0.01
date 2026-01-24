# User Guide (Player)

## Controls (Tk HUD)
This section applies to the legacy desktop HUD (`python hybrid/gui/gui.py`).

- Click a contact to select as **target**
- **F** — Fire weapon (if in FOV + turret arc, power & cooldown OK)
- **P** — Active sensor ping
- **A** — Toggle autopilot override
- **R** — Start/Stop recording to `replay.jsonl`

## Controls (Web GUI)
- Use the **Sensors** panel to select a contact, then **Lock Target**
- Use **Autopilot** panel to engage programs (intercept/match/hold/hold_velocity)
- Use **Weapons** panel to fire (via `fire_weapon` commands)

## Tips
- Stay within the **weapon arc** wedge on the radar to enable firing.
- Targets with **ECM** degrade missile lock; fire closer or use ECCM‑capable missiles.
- PDC will auto‑engage the nearest inbound missile if within arc/range.
