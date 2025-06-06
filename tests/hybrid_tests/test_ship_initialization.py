# tests/hybrid_tests/test_ship_initialization.py

import json
from pathlib import Path
import pytest
from hybrid.ship_factory import create_ship


def test_create_simple_ship(tmp_path):
    cfg = {
        "id": "testship",
        "power": {"primary": {}, "secondary": {}, "tertiary": {}},
        "weapons": {"weapons": []},
        "navigation": {},
        "sensors": {}
    }
    ship_config = {"testship": cfg}
    # Write JSON to a temporary file
    file_path = tmp_path / "ships.json"
    file_path.write_text(json.dumps(ship_config))

    # Load and create ship
    ship_defs = json.loads(file_path.read_text())
    ship = create_ship(ship_defs["testship"])
    assert ship["power"] is not None
    assert ship["weapons"] is not None
    assert ship["navigation"] is not None
    assert ship["sensors"] is not None
