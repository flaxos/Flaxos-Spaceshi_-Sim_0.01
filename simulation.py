# simulation.py — Main simulation loop with sector integration

import time

def simulation_loop(ships, sector_manager):
    tick_rate = 1.0  # seconds per tick
    tick = 0

    while True:
        print(f"\n[TICK {tick}] Updating {len(ships)} ships...")

        for ship in ships:
            old_position = ship.position.copy()
            ship.tick(tick_rate)
            sector_manager.update_ship_position(ship, old_position)

            # Proximity scan for nearby ships (radius = 2000)
            nearby = sector_manager.get_nearby_ships(ship.position, radius=2000)
            nearby_ids = [s.id for s in nearby if s.id != ship.id]

            # Sensor output
            sensor_state = ship.systems.get("sensors")
            detected = sensor_state.get_state()["detected_ships"] if sensor_state else []

            state = ship.get_state()
            pos = state["position"]
            vel = state["velocity"]

            print(f" - [{ship.id}] Pos=({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}) Vel=({vel['x']:.2f}, {vel['y']:.2f}, {vel['z']:.2f}) Nearby: {nearby_ids} Detected: {detected}")

        # Print sector contents after updates
        print("[SECTOR MAP]")
        for sector_key, contents in sector_manager.sectors.items():
            ids = [s.id for s in contents]
            print(f"  Sector {sector_key}: {ids}")

        tick += 1
        time.sleep(tick_rate)
