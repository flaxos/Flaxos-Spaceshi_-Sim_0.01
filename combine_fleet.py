import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser(description="Merge ship JSON files into one fleet")
    parser.add_argument("--fleet-dir", required=True, help="Directory containing ship JSON files")
    args = parser.parse_args()

    ships = {}
    if not os.path.isdir(args.fleet_dir):
        print(f"Fleet directory not found: {args.fleet_dir}")
        return

    for filename in os.listdir(args.fleet_dir):
        if filename.endswith(".json"):
            path = os.path.join(args.fleet_dir, filename)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "id" in data:
                    ships[data["id"]] = data
                elif isinstance(data, dict):
                    ships.update(data)
            except Exception as e:
                print(f"Failed to load {path}: {e}")

    with open("combined_ships.json", "w") as f:
        json.dump(ships, f, indent=2)
    print(f"Wrote {len(ships)} ships to combined_ships.json")


if __name__ == "__main__":
    main()
