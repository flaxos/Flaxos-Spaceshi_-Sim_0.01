"""Focused tests for commands.handlers."""

from commands.handlers import handle_command


def test_handle_command_finds_ship_across_sectors():
    """Ship lookup should traverse all sectors until it finds the target ship."""
    sectors = {
        (0, 0, 0): {
            "ships": {
                "ship_alpha": {
                    "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                    "velocity": {"x": 0.1, "y": 0.2, "z": 0.3},
                }
            }
        },
        (1, 0, 0): {
            "ships": {
                "ship_bravo": {
                    "position": {"x": 4.0, "y": 5.0, "z": 6.0},
                    "velocity": {"x": 0.4, "y": 0.5, "z": 0.6},
                }
            }
        },
    }

    result = handle_command(
        {
            "command_type": "get_position",
            "payload": {"ship": "ship_bravo"},
        },
        sectors,
    )

    assert result == {"position": {"x": 4.0, "y": 5.0, "z": 6.0}}
