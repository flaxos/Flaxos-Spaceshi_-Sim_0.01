"""
Asset Editor Server for Flaxos Spaceship Sim.

Lightweight HTTP server providing a REST API for managing game assets
(ships, scenarios) and serving the editor UI from gui/editor/.
Runs on port 3200, separate from the game GUI on 3100.

Uses only Python stdlib -- no external dependencies required.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Optional

# Optional YAML support -- graceful fallback to JSON-only if unavailable
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Path resolution --------------------------------------------------------
# Project root is two levels up from this file (gui/asset_editor_server.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLEET_DIR = PROJECT_ROOT / "hybrid_fleet"
SCENARIO_DIR = PROJECT_ROOT / "scenarios"
EDITOR_DIR = PROJECT_ROOT / "gui" / "editor"

# Serialisation lock -- protects file reads/writes across request threads
_file_lock = threading.Lock()

REQUIRED_SHIP_FIELDS = {"id", "position", "velocity", "systems"}
REQUIRED_SCENARIO_FIELDS = {"name", "ships"}


# --- Helpers -----------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write a JSON file (write-then-rename for safety)."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    tmp.replace(path)


def _read_scenario(path: Path) -> dict[str, Any]:
    """Read a scenario file, supporting both JSON and YAML."""
    if path.suffix == ".yaml" or path.suffix == ".yml":
        if not HAS_YAML:
            raise ValueError(f"YAML support unavailable; cannot read {path.name}")
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return _read_json(path)


def _scenario_id(path: Path) -> str:
    """Derive a stable scenario ID from its filename (stem)."""
    return path.stem


def _find_scenario_path(scenario_id: str) -> Optional[Path]:
    """Locate a scenario file by ID, checking json/yaml/yml extensions."""
    for ext in (".json", ".yaml", ".yml"):
        candidate = SCENARIO_DIR / f"{scenario_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def _ship_refs_in_scenarios(ship_id: str) -> list[str]:
    """Return scenario IDs that reference the given ship ID."""
    refs: list[str] = []
    for path in SCENARIO_DIR.iterdir():
        if path.suffix not in (".json", ".yaml", ".yml"):
            continue
        try:
            data = _read_scenario(path)
        except Exception:
            continue
        # Ships can live at top-level "ships" list or inside "fleets"
        ships = data.get("ships", [])
        ship_ids = {s.get("id") for s in ships if isinstance(s, dict)}
        for fleet in data.get("fleets", []):
            ship_ids.update(fleet.get("ships", []))
        if ship_id in ship_ids:
            refs.append(_scenario_id(path))
    return refs


def _validate_ship(data: dict[str, Any]) -> list[str]:
    """Return a list of validation errors for a ship definition.

    Enforces server-authoritative constraints on ship asset data:
    - Required field presence
    - ID format
    - Vector component presence
    - Numeric value bounds (mass, thrust, fuel must be positive and finite)
    - Coordinate bounds (within 1 AU)
    """
    import math

    errors: list[str] = []
    missing = REQUIRED_SHIP_FIELDS - set(data.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")
    if "id" in data and not re.match(r"^[a-zA-Z0-9_-]+$", str(data["id"])):
        errors.append("Ship id must be alphanumeric (underscores/hyphens allowed)")
    for vec_field in ("position", "velocity"):
        vec = data.get(vec_field)
        if isinstance(vec, dict) and not {"x", "y", "z"}.issubset(vec.keys()):
            errors.append(f"{vec_field} must have x, y, z components")

    # Numeric bounds validation
    MAX_COORD = 1.5e11  # 1 AU in meters

    def _check_positive(field: str, label: str | None = None) -> None:
        val = data.get(field)
        if val is None:
            return
        try:
            fval = float(val)
        except (ValueError, TypeError):
            errors.append(f"{label or field} must be a number")
            return
        if not math.isfinite(fval):
            errors.append(f"{label or field} must be finite")
        elif fval < 0:
            errors.append(f"{label or field} must be non-negative")

    for field in ("mass", "dry_mass", "max_thrust", "max_fuel", "fuel_level"):
        _check_positive(field)

    # Coordinate bounds
    for vec_field in ("position", "velocity"):
        vec = data.get(vec_field)
        if not isinstance(vec, dict):
            continue
        for axis in ("x", "y", "z"):
            val = vec.get(axis)
            if val is None:
                continue
            try:
                fval = float(val)
            except (ValueError, TypeError):
                errors.append(f"{vec_field}.{axis} must be a number")
                continue
            if not math.isfinite(fval):
                errors.append(f"{vec_field}.{axis} must be finite")
            elif abs(fval) > MAX_COORD:
                errors.append(f"{vec_field}.{axis} exceeds maximum ({MAX_COORD:.0e})")

    return errors


# --- Request Handler ---------------------------------------------------------

class AssetEditorHandler(SimpleHTTPRequestHandler):
    """
    Combined static-file and REST API handler.

    Routes starting with /api/ are handled as JSON REST endpoints.
    Everything else is served as static files from the editor directory.
    """

    # Suppress default stderr logging -- we use the logging module instead
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info(fmt % args)

    # -- Routing helpers ------------------------------------------------------

    def _set_cors(self) -> None:
        """Add CORS headers for local development."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._set_cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json_response({"error": message}, status)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw)

    # -- HTTP verbs -----------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path.startswith("/api/"):
            self._route_api("GET", path)
            return

        # Static files from editor directory
        self._serve_static(path)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._route_api("POST", path)
        else:
            self._error(405, "POST only supported for /api/ routes")

    def do_PUT(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._route_api("PUT", path)
        else:
            self._error(405, "PUT only supported for /api/ routes")

    def do_DELETE(self) -> None:
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            self._route_api("DELETE", path)
        else:
            self._error(405, "DELETE only supported for /api/ routes")

    # -- Static file serving --------------------------------------------------

    def _serve_static(self, url_path: str) -> None:
        """Serve static files from gui/editor/, falling back to index.html."""
        if url_path in ("", "/"):
            url_path = "/index.html"

        # Strip leading /editor/ prefix if present so both / and /editor/ work
        clean = url_path.lstrip("/")
        if clean.startswith("editor/"):
            clean = clean[len("editor/"):]

        file_path = EDITOR_DIR / clean
        if not file_path.exists() or not file_path.is_file():
            self._error(404, f"File not found: {url_path}")
            return

        # Prevent directory traversal
        try:
            file_path.resolve().relative_to(EDITOR_DIR.resolve())
        except ValueError:
            self._error(403, "Forbidden")
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self._set_cors()
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # -- API Router -----------------------------------------------------------

    def _route_api(self, method: str, path: str) -> None:
        """Dispatch API requests to the correct handler."""
        parts = path.rstrip("/").split("/")  # ['', 'api', 'ships', ...]

        try:
            resource = parts[2] if len(parts) > 2 else ""
            resource_id = parts[3] if len(parts) > 3 else None
            action = parts[4] if len(parts) > 4 else None

            if resource == "ships":
                self._handle_ships(method, resource_id, action)
            elif resource == "scenarios":
                self._handle_scenarios(method, resource_id)
            elif resource == "validate" and method == "POST":
                self._handle_validate(resource_id)
            elif resource == "refs" and method == "GET" and resource_id:
                self._handle_refs(resource_id)
            else:
                self._error(404, f"Unknown API route: {path}")
        except json.JSONDecodeError:
            self._error(400, "Invalid JSON in request body")
        except Exception as exc:
            logger.exception("Unhandled error in API handler")
            self._error(500, str(exc))

    # -- Ship endpoints -------------------------------------------------------

    def _handle_ships(self, method: str, ship_id: Optional[str], action: Optional[str]) -> None:
        if method == "GET" and ship_id is None:
            self._list_ships()
        elif method == "GET" and ship_id:
            self._get_ship(ship_id)
        elif method == "POST" and ship_id is None:
            self._create_ship()
        elif method == "POST" and ship_id and action == "duplicate":
            self._duplicate_ship(ship_id)
        elif method == "PUT" and ship_id:
            self._update_ship(ship_id)
        elif method == "DELETE" and ship_id:
            self._delete_ship(ship_id)
        else:
            self._error(405, "Method not allowed")

    def _list_ships(self) -> None:
        ships: list[dict[str, Any]] = []
        with _file_lock:
            for p in sorted(FLEET_DIR.glob("*.json")):
                try:
                    data = _read_json(p)
                    ships.append({
                        "id": data.get("id", p.stem),
                        "name": data.get("name", ""),
                        "class": data.get("class", ""),
                        "faction": data.get("faction", ""),
                    })
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", p.name, exc)
        self._json_response(ships)

    def _get_ship(self, ship_id: str) -> None:
        path = FLEET_DIR / f"{ship_id}.json"
        with _file_lock:
            if not path.exists():
                self._error(404, f"Ship not found: {ship_id}")
                return
            self._json_response(_read_json(path))

    def _create_ship(self) -> None:
        data = self._read_body()
        errors = _validate_ship(data)
        if errors:
            self._json_response({"errors": errors}, 400)
            return
        ship_id = data["id"]
        path = FLEET_DIR / f"{ship_id}.json"
        with _file_lock:
            if path.exists():
                self._error(409, f"Ship already exists: {ship_id}")
                return
            _write_json(path, data)
        self._json_response({"id": ship_id, "status": "created"}, 201)

    def _update_ship(self, ship_id: str) -> None:
        data = self._read_body()
        errors = _validate_ship(data)
        if errors:
            self._json_response({"errors": errors}, 400)
            return
        path = FLEET_DIR / f"{ship_id}.json"
        with _file_lock:
            if not path.exists():
                self._error(404, f"Ship not found: {ship_id}")
                return
            _write_json(path, data)
        self._json_response({"id": ship_id, "status": "updated"})

    def _delete_ship(self, ship_id: str) -> None:
        path = FLEET_DIR / f"{ship_id}.json"
        with _file_lock:
            if not path.exists():
                self._error(404, f"Ship not found: {ship_id}")
                return
            refs = _ship_refs_in_scenarios(ship_id)
            if refs:
                self._json_response({
                    "error": "Ship is referenced by scenarios",
                    "referenced_by": refs,
                }, 409)
                return
            path.unlink()
        self._json_response({"id": ship_id, "status": "deleted"})

    def _duplicate_ship(self, ship_id: str) -> None:
        data = self._read_body()
        new_id = data.get("new_id")
        if not new_id:
            self._error(400, "new_id is required for duplication")
            return
        if not re.match(r"^[a-zA-Z0-9_-]+$", new_id):
            self._error(400, "new_id must be alphanumeric (underscores/hyphens allowed)")
            return
        src = FLEET_DIR / f"{ship_id}.json"
        dst = FLEET_DIR / f"{new_id}.json"
        with _file_lock:
            if not src.exists():
                self._error(404, f"Source ship not found: {ship_id}")
                return
            if dst.exists():
                self._error(409, f"Ship already exists: {new_id}")
                return
            ship_data = _read_json(src)
            ship_data["id"] = new_id
            if "name" in ship_data:
                ship_data["name"] = f"{ship_data['name']} (copy)"
            _write_json(dst, ship_data)
        self._json_response({"id": new_id, "status": "duplicated"}, 201)

    # -- Scenario endpoints ---------------------------------------------------

    def _handle_scenarios(self, method: str, scenario_id: Optional[str]) -> None:
        if method == "GET" and scenario_id is None:
            self._list_scenarios()
        elif method == "GET" and scenario_id:
            self._get_scenario(scenario_id)
        elif method == "POST" and scenario_id is None:
            self._create_scenario()
        elif method == "PUT" and scenario_id:
            self._update_scenario(scenario_id)
        elif method == "DELETE" and scenario_id:
            self._delete_scenario(scenario_id)
        else:
            self._error(405, "Method not allowed")

    def _list_scenarios(self) -> None:
        scenarios: list[dict[str, Any]] = []
        with _file_lock:
            for p in sorted(SCENARIO_DIR.iterdir()):
                if p.suffix not in (".json", ".yaml", ".yml"):
                    continue
                try:
                    data = _read_scenario(p)
                    meta = data.get("metadata", data.get("mission", {}))
                    scenarios.append({
                        "id": _scenario_id(p),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "format": p.suffix.lstrip("."),
                        "tags": meta.get("tags", []) if isinstance(meta, dict) else [],
                    })
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", p.name, exc)
        self._json_response(scenarios)

    def _get_scenario(self, scenario_id: str) -> None:
        with _file_lock:
            path = _find_scenario_path(scenario_id)
            if not path:
                self._error(404, f"Scenario not found: {scenario_id}")
                return
            self._json_response(_read_scenario(path))

    def _create_scenario(self) -> None:
        data = self._read_body()
        missing = REQUIRED_SCENARIO_FIELDS - set(data.keys())
        if missing:
            self._error(400, f"Missing required fields: {', '.join(sorted(missing))}")
            return
        # Derive ID from name if no explicit id provided
        scenario_id = data.get("id", re.sub(r"[^a-zA-Z0-9]+", "_", data["name"]).strip("_").lower())
        path = SCENARIO_DIR / f"{scenario_id}.json"
        with _file_lock:
            if path.exists():
                self._error(409, f"Scenario already exists: {scenario_id}")
                return
            _write_json(path, data)
        self._json_response({"id": scenario_id, "status": "created"}, 201)

    def _update_scenario(self, scenario_id: str) -> None:
        data = self._read_body()
        with _file_lock:
            path = _find_scenario_path(scenario_id)
            if not path:
                self._error(404, f"Scenario not found: {scenario_id}")
                return
            # Always write back as JSON regardless of original format
            dst = SCENARIO_DIR / f"{scenario_id}.json"
            _write_json(dst, data)
            # Remove old YAML file if format changed
            if path != dst and path.exists():
                path.unlink()
        self._json_response({"id": scenario_id, "status": "updated"})

    def _delete_scenario(self, scenario_id: str) -> None:
        with _file_lock:
            path = _find_scenario_path(scenario_id)
            if not path:
                self._error(404, f"Scenario not found: {scenario_id}")
                return
            path.unlink()
        self._json_response({"id": scenario_id, "status": "deleted"})

    # -- Validation & refs ----------------------------------------------------

    def _handle_validate(self, asset_type: Optional[str]) -> None:
        if asset_type == "ship":
            data = self._read_body()
            errors = _validate_ship(data)
            self._json_response({"valid": len(errors) == 0, "errors": errors})
        else:
            self._error(400, f"Unknown validation type: {asset_type}")

    def _handle_refs(self, asset_id: str) -> None:
        """Find all references to an asset across scenarios and fleet files."""
        refs: dict[str, list[str]] = {"scenarios": [], "ships": []}
        with _file_lock:
            refs["scenarios"] = _ship_refs_in_scenarios(asset_id)
        self._json_response({"id": asset_id, "references": refs})


# --- Server entry point ------------------------------------------------------

def run(host: str = "0.0.0.0", port: int = 3200) -> None:
    """Start the asset editor HTTP server."""
    # Ensure asset directories exist
    FLEET_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

    server = HTTPServer((host, port), AssetEditorHandler)
    logger.info("Asset Editor server running on http://%s:%d", host, port)
    logger.info("Fleet dir : %s", FLEET_DIR)
    logger.info("Scenario dir: %s", SCENARIO_DIR)
    logger.info("Editor UI : %s", EDITOR_DIR)
    if not HAS_YAML:
        logger.warning("PyYAML not installed -- YAML scenarios will be read-only")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down asset editor server")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Flaxos Asset Editor Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=3200, help="Listen port (default: 3200)")
    args = parser.parse_args()
    run(host=args.host, port=args.port)
