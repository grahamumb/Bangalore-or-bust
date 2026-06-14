"""Cross-session persistence.

state.json   - the single source of truth for resuming: cumulative distance
               walked across all sessions, plus the current town + its facts.
sessions.json - append-only log of every walk session with its stats.

All writes are atomic (temp file + os.replace) so a crash mid-write can't
corrupt the file.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import config

_lock = threading.Lock()


def _atomic_write(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_state():
    """Return persisted state, with defaults filled in."""
    state = _read_json(config.STATE_FILE, {})
    state.setdefault("cumulative_distance_m", 0.0)
    state.setdefault("town", None)  # {name, region, population, fun_fact, famous_person}
    return state


def save_cumulative_distance(distance_m):
    with _lock:
        state = load_state()
        state["cumulative_distance_m"] = float(distance_m)
        _atomic_write(config.STATE_FILE, state)


def save_town(town):
    """Persist the current town block (dict) so we don't re-query the LLM."""
    with _lock:
        state = load_state()
        state["town"] = town
        _atomic_write(config.STATE_FILE, state)


class Session:
    """Tracks one walk and keeps its record up to date in sessions.json."""

    def __init__(self, start_distance_m):
        self.id = uuid.uuid4().hex[:8]
        self.start_distance_m = start_distance_m
        self.start_monotonic = time.monotonic()
        self.start_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.distance_m = 0.0
        self.duration_s = 0.0
        self._index = None  # position of this session's record in the file
        self._persist(finalize=False)

    def _record(self, finalize):
        avg_mph = 0.0
        if self.duration_s > 0:
            avg_mph = (self.distance_m / config.METERS_PER_MILE) / (self.duration_s / 3600.0)
        return {
            "id": self.id,
            "start_iso": self.start_iso,
            "end_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") if finalize else None,
            "distance_m": round(self.distance_m, 1),
            "distance_mi": round(self.distance_m / config.METERS_PER_MILE, 3),
            "duration_s": round(self.duration_s, 1),
            "avg_speed_mph": round(avg_mph, 2),
        }

    def _persist(self, finalize):
        with _lock:
            sessions = _read_json(config.SESSIONS_FILE, [])
            record = self._record(finalize)
            if self._index is None:
                self._index = len(sessions)
                sessions.append(record)
            else:
                sessions[self._index] = record
            _atomic_write(config.SESSIONS_FILE, sessions)

    def update(self, session_distance_m):
        """Called each tick with the distance walked so far this session."""
        self.distance_m = session_distance_m
        self.duration_s = time.monotonic() - self.start_monotonic
        self._persist(finalize=False)

    def finalize(self):
        self.duration_s = time.monotonic() - self.start_monotonic
        self._persist(finalize=True)
