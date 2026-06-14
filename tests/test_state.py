import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_state_module(tmp_path):
    """Reload config + state pointed at temp files."""
    import config
    config.STATE_FILE = str(tmp_path / "state.json")
    config.SESSIONS_FILE = str(tmp_path / "sessions.json")
    import state
    importlib.reload(state)
    return state


def test_load_defaults(tmp_path):
    state = _fresh_state_module(tmp_path)
    s = state.load_state()
    assert s["cumulative_distance_m"] == 0.0
    assert s["town"] is None


def test_save_and_reload_cumulative(tmp_path):
    state = _fresh_state_module(tmp_path)
    state.save_cumulative_distance(1234.5)
    assert state.load_state()["cumulative_distance_m"] == 1234.5
    # File is valid JSON on disk (atomic write left no .tmp).
    with open(state.config.STATE_FILE) as fh:
        assert json.load(fh)["cumulative_distance_m"] == 1234.5
    assert not os.path.exists(state.config.STATE_FILE + ".tmp")


def test_save_town(tmp_path):
    state = _fresh_state_module(tmp_path)
    town = {"name": "Lyon", "region": "AURA", "population": "500k"}
    state.save_town(town)
    assert state.load_state()["town"]["name"] == "Lyon"


def test_session_lifecycle(tmp_path):
    state = _fresh_state_module(tmp_path)
    session = state.Session(start_distance_m=100.0)
    session.update(session_distance_m=50.0)
    session.finalize()

    with open(state.config.SESSIONS_FILE) as fh:
        sessions = json.load(fh)
    assert len(sessions) == 1
    rec = sessions[0]
    assert rec["distance_m"] == 50.0
    assert rec["end_iso"] is not None
    assert rec["avg_speed_mph"] >= 0
