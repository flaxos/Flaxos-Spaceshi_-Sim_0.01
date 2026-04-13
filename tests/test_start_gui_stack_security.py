"""Regression coverage for secure launcher URL handling."""

from tools.start_gui_stack import _append_query_param


def test_append_query_param_adds_new_value():
    assert (
        _append_query_param("http://localhost:3100/", "game_code", "abc123")
        == "http://localhost:3100/?game_code=abc123"
    )


def test_append_query_param_replaces_existing_value():
    assert (
        _append_query_param(
            "http://localhost:3100/?game_code=old&foo=bar",
            "game_code",
            "new",
        )
        == "http://localhost:3100/?game_code=new&foo=bar"
    )
