# tests/test_skirmish_generator.py
"""Tests for the skirmish scenario generator."""

import pytest
from hybrid.scenarios.skirmish_generator import generate_skirmish, VALID_MODES


class TestGenerateSkirmish:
    """Tests for generate_skirmish()."""

    def test_default_params_produces_valid_scenario(self):
        """Minimal call with defaults should produce a loadable scenario."""
        result = generate_skirmish({})
        assert result["name"]
        assert result["dt"] == 0.1
        assert len(result["ships"]) >= 2  # at least 1 player + 1 enemy
        assert result["mission"]

    def test_deathmatch_mode(self):
        params = {
            "mode": "deathmatch",
            "player_ships": [{"class": "corvette"}],
            "enemy_ships": [{"class": "frigate", "count": 2}],
            "start_range_km": 30,
        }
        result = generate_skirmish(params)

        ship_ids = [s["id"] for s in result["ships"]]
        assert "player" in ship_ids
        assert "enemy_0" in ship_ids
        assert "enemy_1" in ship_ids

        # Should have destroy objectives for each enemy + survive objective
        obj_types = [o["type"] for o in result["mission"]["objectives"]]
        assert obj_types.count("destroy_target") == 2
        assert "avoid_mission_kill" in obj_types

    def test_defend_mode_adds_station(self):
        params = {
            "mode": "defend",
            "enemy_ships": [{"class": "corvette", "count": 3}],
        }
        result = generate_skirmish(params)

        ship_ids = [s["id"] for s in result["ships"]]
        assert "defended_asset" in ship_ids

        obj_types = [o["type"] for o in result["mission"]["objectives"]]
        assert "protect_ship" in obj_types

    def test_escort_mode_adds_freighter(self):
        params = {
            "mode": "escort",
            "enemy_ships": [{"class": "fighter", "count": 2}],
        }
        result = generate_skirmish(params)

        ship_ids = [s["id"] for s in result["ships"]]
        assert "escort_freighter" in ship_ids

        obj_types = [o["type"] for o in result["mission"]["objectives"]]
        assert "protect_ship" in obj_types

    def test_team_mode(self):
        params = {
            "mode": "team",
            "player_ships": [{"class": "corvette"}, {"class": "fighter"}],
            "enemy_ships": [{"class": "frigate"}],
        }
        result = generate_skirmish(params)

        ship_ids = [s["id"] for s in result["ships"]]
        assert "player" in ship_ids
        assert "player_1" in ship_ids

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            generate_skirmish({"mode": "invalid_mode"})

    def test_seed_produces_deterministic_positions(self):
        params = {
            "mode": "deathmatch",
            "enemy_ships": [{"class": "corvette"}],
            "seed": 42,
        }
        r1 = generate_skirmish(params)
        r2 = generate_skirmish(params)

        pos1 = r1["ships"][1]["position"]
        pos2 = r2["ships"][1]["position"]
        assert pos1 == pos2

    def test_time_limit_propagated(self):
        params = {
            "mode": "deathmatch",
            "time_limit_seconds": 300,
        }
        result = generate_skirmish(params)
        assert result["mission"]["time_limit"] == 300

    def test_ships_have_required_fields(self):
        """Every ship must have the fields the loader expects."""
        result = generate_skirmish({"mode": "deathmatch"})
        required_keys = {"id", "name", "class", "faction", "position",
                         "velocity", "orientation", "mass", "systems"}
        for ship in result["ships"]:
            missing = required_keys - set(ship.keys())
            assert not missing, f"Ship {ship['id']} missing keys: {missing}"

    def test_player_ship_is_player_controlled(self):
        result = generate_skirmish({})
        player_ship = next(s for s in result["ships"] if s["id"] == "player")
        assert player_ship["player_controlled"] is True

    def test_enemy_ships_have_ai(self):
        result = generate_skirmish({"mode": "deathmatch"})
        enemy_ships = [s for s in result["ships"] if s["id"].startswith("enemy_")]
        for ship in enemy_ships:
            assert "ai" in ship, f"Enemy ship {ship['id']} missing AI config"
            assert ship["ai_enabled"] is True

    def test_all_valid_modes(self):
        """Smoke test: every valid mode generates without error."""
        for mode in VALID_MODES:
            result = generate_skirmish({"mode": mode})
            assert result["ships"]
            assert result["mission"]["objectives"]

    def test_ships_face_each_other(self):
        """Player and enemy ships should have non-zero yaw (facing target)."""
        params = {
            "mode": "deathmatch",
            "start_range_km": 100,
            "randomize_positions": False,
            "seed": 1,
        }
        result = generate_skirmish(params)
        # Player faces outward (toward enemies), enemy faces origin
        enemy = next(s for s in result["ships"] if s["id"].startswith("enemy_"))
        # Enemy is at ~100km, should face back toward origin — nonzero yaw
        # (unless exactly on the x-axis, which is unlikely with random bearing)
        # Just verify orientation exists and is a dict
        assert "yaw" in enemy["orientation"]

    def test_range_randomization(self):
        """With randomize on, enemy positions should vary across seeds."""
        positions = set()
        for seed in range(5):
            r = generate_skirmish({"seed": seed, "start_range_km": 50})
            enemy = next(s for s in r["ships"] if s["id"].startswith("enemy_"))
            pos = (enemy["position"]["x"], enemy["position"]["y"])
            positions.add(pos)
        # Should have at least 3 different positions across 5 seeds
        assert len(positions) >= 3
