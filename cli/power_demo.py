"""Command-line demo for the power management system."""
import argparse
from hybrid.systems.power_management_system import PowerManagementSystem


def main():
    parser = argparse.ArgumentParser(description="Power management demo")
    parser.add_argument("action", choices=["status", "request", "reroute"], help="Action to perform")
    parser.add_argument("--amount", type=float, default=0.0, help="Amount of power to request or reroute")
    parser.add_argument("--system", default="propulsion", help="System name for power request")
    parser.add_argument("--from_layer", default="primary", help="Layer to reroute from")
    parser.add_argument("--to_layer", default="secondary", help="Layer to reroute to")
    args = parser.parse_args()

    pm = PowerManagementSystem({})
    pm.tick(1.0, None, None)

    if args.action == "status":
        print(pm.get_state())
    elif args.action == "request":
        success = pm.request_power(args.amount, args.system)
        print({"success": success, "state": pm.get_state()})
    elif args.action == "reroute":
        moved = pm.reroute_power(args.amount, args.from_layer, args.to_layer)
        print({"moved": moved, "state": pm.get_state()})


if __name__ == "__main__":
    main()

