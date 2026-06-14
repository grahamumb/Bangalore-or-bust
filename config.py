"""Central configuration, read from environment variables.

A tiny .env loader is included so you can keep secrets in a local .env file
without depending on python-dotenv.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    """Populate os.environ from a .env file if present (does not override
    variables already set in the real environment)."""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


def _bool(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


# --- Secrets ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# --- Hardware / serial ---
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/serial0")
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))

# --- LLM ---
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")

# --- Behaviour ---
UPDATE_INTERVAL_SEC = int(os.environ.get("UPDATE_INTERVAL_SEC", "60"))
DISTANCE_UNIT = os.environ.get("DISTANCE_UNIT", "miles").strip().lower()
GPX_FILE = os.environ.get("GPX_FILE", os.path.join(BASE_DIR, "route.gpx"))

# --- Dev flags ---
FAKE_SERIAL = _bool("FAKE_SERIAL")
FAKE_LLM = _bool("FAKE_LLM")

# --- Paths ---
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "sessions.json")

# Unit conversion to meters.
METERS_PER_MILE = 1609.344
METERS_PER_KM = 1000.0


def meters_from_distance(value):
    """Convert a treadmill distance reading (in DISTANCE_UNIT) to meters."""
    if value is None:
        return 0.0
    if DISTANCE_UNIT == "km":
        return value * METERS_PER_KM
    return value * METERS_PER_MILE
