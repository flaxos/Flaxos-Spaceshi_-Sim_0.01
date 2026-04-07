"""Tests for inter-station messaging commands (station_message / get_station_messages).

These commands let crew members at different stations send text messages
to each other on the same ship. Messages are stored per-ship and filtered
by station when retrieved.
"""

import time

from server.stations.station_dispatch import StationAwareDispatcher
from server.stations.station_manager import StationManager
from server.stations.station_commands import register_station_commands
from server.stations.station_types import StationType


def _setup_two_stations():
    """Create a dispatcher with two clients on the same ship at different stations.

    Returns:
        (dispatcher, manager, client_ids) tuple.
    """
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("helm_client", "Helm Officer")
    manager.register_client("tac_client", "Tactical Officer")

    manager.assign_to_ship("helm_client", "ship_alpha")
    manager.assign_to_ship("tac_client", "ship_alpha")

    manager.claim_station("helm_client", "ship_alpha", StationType.HELM)
    manager.claim_station("tac_client", "ship_alpha", StationType.TACTICAL)

    return dispatcher, manager


# ---------------------------------------------------------------------------
# station_message: basic send
# ---------------------------------------------------------------------------

def test_send_message_to_station():
    """A station can send a directed message to another station."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "Firing solution ready?"},
    )

    assert result.success is True
    assert result.data is not None
    assert result.data["from_station"] == "helm"
    assert result.data["to"] == "tactical"
    assert result.data["text"] == "Firing solution ready?"
    assert "id" in result.data
    assert "timestamp" in result.data


def test_send_broadcast_message():
    """A station can broadcast a message to all stations."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "tac_client", "ship_alpha", "station_message",
        {"to": "all", "text": "Contact bearing 045"},
    )

    assert result.success is True
    assert result.data["to"] == "all"


def test_send_message_empty_text_rejected():
    """Messages with empty text are rejected."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": ""},
    )

    assert result.success is False
    assert "text" in result.message.lower()


def test_send_message_whitespace_only_rejected():
    """Messages with whitespace-only text are rejected (stripped to empty)."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "   "},
    )

    assert result.success is False


def test_send_message_invalid_target_station():
    """Messages to a non-existent station type are rejected."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "nonexistent", "text": "hello"},
    )

    assert result.success is False
    assert "invalid" in result.message.lower() or "station" in result.message.lower()


def test_send_message_text_truncated_at_500():
    """Messages longer than 500 characters are silently truncated."""
    dispatcher, _ = _setup_two_stations()

    long_text = "A" * 600
    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": long_text},
    )

    assert result.success is True
    assert len(result.data["text"]) == 500


def test_send_message_requires_station_claim():
    """A client without a claimed station cannot send messages."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("orphan", "Orphan")
    manager.assign_to_ship("orphan", "ship_alpha")
    # No station claimed

    result = dispatcher.dispatch(
        "orphan", "ship_alpha", "station_message",
        {"to": "helm", "text": "hello"},
    )

    assert result.success is False
    assert "station" in result.message.lower()


def test_send_message_requires_ship_assignment():
    """A client not assigned to a ship cannot send messages."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("orphan", "Orphan")
    # No ship assignment

    result = dispatcher.dispatch(
        "orphan", "", "station_message",
        {"to": "helm", "text": "hello"},
    )

    assert result.success is False


# ---------------------------------------------------------------------------
# get_station_messages: retrieval
# ---------------------------------------------------------------------------

def test_get_messages_returns_directed_messages():
    """A station sees messages directed to it."""
    dispatcher, _ = _setup_two_stations()

    # Helm sends to tactical
    dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "Ready to fire"},
    )

    result = dispatcher.dispatch(
        "tac_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    assert len(messages) >= 1
    assert any(m["text"] == "Ready to fire" for m in messages)


def test_get_messages_returns_broadcasts():
    """A station sees broadcast messages (to='all')."""
    dispatcher, _ = _setup_two_stations()

    # Tactical broadcasts
    dispatcher.dispatch(
        "tac_client", "ship_alpha", "station_message",
        {"to": "all", "text": "All hands, brace"},
    )

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    assert any(m["text"] == "All hands, brace" for m in messages)


def test_get_messages_returns_own_sent_messages():
    """A station sees messages it sent (from_station matches)."""
    dispatcher, _ = _setup_two_stations()

    dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "Outbound message"},
    )

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    assert any(m["text"] == "Outbound message" for m in messages)


def test_get_messages_filters_by_station():
    """A station does not see messages directed to other stations (unless captain)."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("helm_client", "Helm")
    manager.register_client("tac_client", "Tactical")
    manager.register_client("ops_client", "Ops")

    manager.assign_to_ship("helm_client", "ship_alpha")
    manager.assign_to_ship("tac_client", "ship_alpha")
    manager.assign_to_ship("ops_client", "ship_alpha")

    manager.claim_station("helm_client", "ship_alpha", StationType.HELM)
    manager.claim_station("tac_client", "ship_alpha", StationType.TACTICAL)
    manager.claim_station("ops_client", "ship_alpha", StationType.OPS)

    # Helm sends to tactical only
    dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "For tactical eyes only"},
    )

    # Ops should NOT see this message (not sender, not recipient, not broadcast)
    result = dispatcher.dispatch(
        "ops_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    assert not any(m["text"] == "For tactical eyes only" for m in messages)


def test_captain_sees_all_messages():
    """Captain station sees all messages regardless of recipient."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("helm_client", "Helm")
    manager.register_client("tac_client", "Tactical")
    manager.register_client("cap_client", "Captain")

    manager.assign_to_ship("helm_client", "ship_alpha")
    manager.assign_to_ship("tac_client", "ship_alpha")
    manager.assign_to_ship("cap_client", "ship_alpha")

    manager.claim_station("helm_client", "ship_alpha", StationType.HELM)
    manager.claim_station("tac_client", "ship_alpha", StationType.TACTICAL)
    manager.claim_station("cap_client", "ship_alpha", StationType.CAPTAIN)

    # Helm sends to tactical (not captain)
    dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "Private message"},
    )

    # Captain should still see it
    result = dispatcher.dispatch(
        "cap_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    assert any(m["text"] == "Private message" for m in messages)


def test_since_id_filters_old_messages():
    """The since_id parameter filters out already-seen messages."""
    dispatcher, _ = _setup_two_stations()

    # Send two messages
    r1 = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "all", "text": "First"},
    )
    first_id = r1.data["id"]

    dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "all", "text": "Second"},
    )

    # Request only messages after the first
    result = dispatcher.dispatch(
        "tac_client", "ship_alpha", "get_station_messages",
        {"since_id": first_id},
    )

    assert result.success is True
    messages = result.data["messages"]
    texts = [m["text"] for m in messages]
    assert "Second" in texts
    assert "First" not in texts


def test_messages_scoped_to_ship():
    """Messages on one ship are not visible to crew on a different ship."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("alpha_helm", "Alpha Helm")
    manager.register_client("bravo_helm", "Bravo Helm")

    manager.assign_to_ship("alpha_helm", "ship_alpha")
    manager.assign_to_ship("bravo_helm", "ship_bravo")

    manager.claim_station("alpha_helm", "ship_alpha", StationType.HELM)
    manager.claim_station("bravo_helm", "ship_bravo", StationType.HELM)

    # Alpha sends a message
    dispatcher.dispatch(
        "alpha_helm", "ship_alpha", "station_message",
        {"to": "all", "text": "Alpha only"},
    )

    # Bravo should see nothing
    result = dispatcher.dispatch(
        "bravo_helm", "ship_bravo", "get_station_messages", {},
    )

    assert result.success is True
    assert len(result.data["messages"]) == 0


def test_message_store_caps_at_200():
    """The per-ship message store caps at 200 messages, dropping oldest."""
    dispatcher, _ = _setup_two_stations()

    # Send 210 messages
    for i in range(210):
        dispatcher.dispatch(
            "helm_client", "ship_alpha", "station_message",
            {"to": "all", "text": f"msg_{i}"},
        )

    result = dispatcher.dispatch(
        "tac_client", "ship_alpha", "get_station_messages", {},
    )

    assert result.success is True
    messages = result.data["messages"]
    # The store keeps 200, get_station_messages returns all visible to this station
    # The earliest messages (msg_0 through msg_9) should have been evicted
    texts = {m["text"] for m in messages}
    assert "msg_0" not in texts
    assert "msg_209" in texts


def test_message_default_to_is_all():
    """When 'to' is omitted, the message defaults to broadcast ('all')."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"text": "No target specified"},
    )

    assert result.success is True
    assert result.data["to"] == "all"


def test_message_includes_player_name():
    """Messages include the sender's player name for display."""
    dispatcher, _ = _setup_two_stations()

    result = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "tactical", "text": "Check this"},
    )

    assert result.success is True
    assert result.data["from_player"] == "Helm Officer"


def test_message_ids_increment():
    """Each message gets a unique incrementing ID."""
    dispatcher, _ = _setup_two_stations()

    r1 = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "all", "text": "first"},
    )
    r2 = dispatcher.dispatch(
        "helm_client", "ship_alpha", "station_message",
        {"to": "all", "text": "second"},
    )

    assert r2.data["id"] > r1.data["id"]
