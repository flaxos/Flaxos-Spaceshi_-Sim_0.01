import argparse
import json
import os
import sys


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def load_ship_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def run_smoke(config_path: str, ticks: int, dt: float) -> dict:
    from hybrid.simulator import Simulator

    simulator = Simulator(dt=dt)
    ship_config = load_ship_config(config_path)
    ship_id = ship_config.get("id") or "android_smoke_ship"
    simulator.add_ship(ship_id, ship_config)
    simulator.start()

    for _ in range(ticks):
        simulator.tick()

    ship_state = simulator.get_ship(ship_id).get_state()
    return {
        "ok": True,
        "ticks": ticks,
        "dt": dt,
        "time": simulator.time,
        "ship": ship_id,
        "position": ship_state.get("position"),
        "velocity": ship_state.get("velocity"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Android/Pydroid smoke test for core sim import + tick."
    )
    parser.add_argument(
        "--ship-config",
        default=os.path.join("fleet_json", "sample_ship.json"),
        help="Path to ship JSON config (relative to repo root).",
    )
    parser.add_argument("--ticks", type=int, default=3)
    parser.add_argument("--dt", type=float, default=0.1)
    args = parser.parse_args()

    config_path = os.path.join(ROOT_DIR, args.ship_config)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Ship config not found: {config_path}")

    result = run_smoke(config_path=config_path, ticks=args.ticks, dt=args.dt)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
