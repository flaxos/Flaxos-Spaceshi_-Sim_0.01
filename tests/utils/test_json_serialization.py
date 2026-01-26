import json

import pytest

from server.run_server import _json_default


def test_json_default_handles_sets_and_tuples():
    payload = {
        "tuple": (1, 2, 3),
        "set": {"a", "b"}
    }

    encoded = json.dumps(payload, default=_json_default)
    decoded = json.loads(encoded)

    assert decoded["tuple"] == [1, 2, 3]
    assert sorted(decoded["set"]) == ["a", "b"]


def test_json_default_handles_numpy_scalars_and_arrays():
    np = pytest.importorskip("numpy")

    payload = {
        "flag": np.bool_(True),
        "count": np.int64(5),
        "values": np.array([1, 2, 3])
    }

    encoded = json.dumps(payload, default=_json_default)
    decoded = json.loads(encoded)

    assert decoded["flag"] is True
    assert decoded["count"] == 5
    assert decoded["values"] == [1, 2, 3]
