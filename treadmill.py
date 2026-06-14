"""Bangalore-or-bust — main Pi orchestrator.

Every UPDATE_INTERVAL_SEC we ask the ESP32-CAM for 4 photos of the treadmill
console, send them to Claude Haiku 4.5 to read speed/distance/time, advance our
position along the GPX route by the LLM-reported distance, and (when we cross
into a new town) fetch some facts about it. State persists across runs so a
restart resumes where we left off.
"""
import atexit
import logging
import os
import signal
import threading
import time

from flask import Flask, jsonify, render_template, request
import gpxpy
import requests
from geopy.distance import geodesic

import camera_serial
import config
import geocode
import llm
import state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("treadmill")

app = Flask(__name__)

os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)

# --- Load GPX path ---
path_coords = []
try:
    with open(config.GPX_FILE) as gpx_file:
        gpx = gpxpy.parse(gpx_file)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    path_coords.append((point.latitude, point.longitude))
except FileNotFoundError:
    log.warning("%s not found. Defaulting to Chicago coords.", config.GPX_FILE)
    path_coords = [(41.8781, -87.6298), (41.8788, -87.6359)]

# --- Live state shared with the frontend ---
current_stats = {
    "speed_mph": 0.0,
    "lat": path_coords[0][0],
    "lng": path_coords[0][1],
    "distance_mi": 0.0,
    "time_minutes": 0.0,
    "calories": 0,
    "town": None,
}
_stats_lock = threading.Lock()

# Holds the active Session so shutdown handlers can finalize it.
_active_session = None


def interpolate_position(coords, distance_m):
    """Interpolate a lat/lng along ``coords`` at a given distance (meters)."""
    accumulated_dist = 0.0
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        segment_dist = geodesic(p1, p2).meters
        if accumulated_dist + segment_dist >= distance_m:
            over_dist = distance_m - accumulated_dist
            ratio = over_dist / segment_dist if segment_dist else 0
            lat = p1[0] + (p2[0] - p1[0]) * ratio
            lng = p1[1] + (p2[1] - p1[1]) * ratio
            return lat, lng
        accumulated_dist += segment_dist
    return coords[-1]


def calculate_position(distance_m):
    """Interpolate a lat/lng along the loaded GPX path at a given distance."""
    return interpolate_position(path_coords, distance_m)


def _maybe_update_town(lat, lng, persisted_state):
    """Reverse-geocode the position; if the town changed, fetch + cache facts."""
    town_name, region = geocode.reverse_geocode(lat, lng)
    if not town_name:
        return persisted_state.get("town")

    current_town = persisted_state.get("town") or {}
    if current_town.get("name") == town_name:
        return current_town  # unchanged

    log.info("Entered new town: %s, %s", town_name, region)
    try:
        facts = llm.town_facts(town_name, region)
    except Exception as exc:  # noqa: BLE001 - never let town facts kill the loop
        log.warning("town_facts failed: %s", exc)
        facts = {"population": None, "fun_fact": None, "famous_person": None}

    town = {"name": town_name, "region": region, **facts}
    state.save_town(town)
    persisted_state["town"] = town
    return town


def update_loop():
    """Background thread: capture -> read -> advance position -> persist."""
    global _active_session
    persisted = state.load_state()
    cumulative_start_m = persisted["cumulative_distance_m"]
    session = state.Session(cumulative_start_m)
    _active_session = session

    # Resume position and town from persisted state.
    lat, lng = calculate_position(cumulative_start_m)
    with _stats_lock:
        current_stats["lat"], current_stats["lng"] = lat, lng
        current_stats["town"] = persisted.get("town")

    log.info("Resuming at %.1f m cumulative.", cumulative_start_m)

    last_reading = {"speed_mph": 0.0, "distance_mi": 0.0, "time_minutes": 0.0, "calories": 0}

    while True:
        try:
            frames = camera_serial.capture_frames()
            if not frames:
                log.warning("no frames captured")
            else:
                reading = llm.read_display(frames)
                # Keep previous values for anything the LLM couldn't read.
                for key in last_reading:
                    if reading.get(key) is not None:
                        last_reading[key] = reading[key]

                session_distance_m = config.meters_from_distance(last_reading["distance_mi"])
                total_m = cumulative_start_m + session_distance_m
                lat, lng = calculate_position(total_m)

                town = _maybe_update_town(lat, lng, persisted)

                with _stats_lock:
                    current_stats["speed_mph"] = last_reading["speed_mph"] or 0.0
                    current_stats["distance_mi"] = total_m / config.METERS_PER_MILE
                    current_stats["time_minutes"] = last_reading["time_minutes"] or 0.0
                    current_stats["calories"] = last_reading["calories"] or 0
                    current_stats["lat"], current_stats["lng"] = lat, lng
                    current_stats["town"] = town

                state.save_cumulative_distance(total_m)
                session.update(session_distance_m)
                log.info("Read: %.2f mph, %.3f mi (total %.3f mi)",
                         last_reading["speed_mph"] or 0.0,
                         last_reading["distance_mi"] or 0.0,
                         total_m / config.METERS_PER_MILE)
        except Exception as exc:  # noqa: BLE001 - loop must survive transient errors
            log.exception("update loop error: %s", exc)

        time.sleep(config.UPDATE_INTERVAL_SEC)


# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html", gmaps_key=config.GOOGLE_MAPS_API_KEY)


@app.route("/data")
def get_data():
    with _stats_lock:
        return jsonify(dict(current_stats))


@app.route("/route")
def get_route():
    """Downsampled route polyline for the mini-map (cap ~500 points)."""
    step = max(1, len(path_coords) // 500)
    coords = [[lat, lng] for lat, lng in path_coords[::step]]
    return jsonify(coords)


@app.route("/save_screenshot", methods=["POST"])
def save_screenshot():
    """Fetch the current view from the Street View Static API and save a JPEG."""
    data = request.get_json(force=True) or {}
    lat, lng = data.get("lat"), data.get("lng")
    if lat is None or lng is None:
        return jsonify({"status": "error", "message": "missing lat/lng"}), 400
    heading = data.get("heading", 0)
    pitch = data.get("pitch", 0)

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/streetview",
            params={
                "size": "640x640",
                "location": f"{lat},{lng}",
                "heading": heading,
                "pitch": pitch,
                "fov": 90,
                "key": config.GOOGLE_MAPS_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"status": "error", "message": str(exc)}), 502

    # Google returns a small "no imagery" placeholder PNG rather than a 404.
    if not resp.headers.get("Content-Type", "").startswith("image"):
        return jsonify({"status": "error", "message": "no imagery here"}), 404

    filename = f"walk_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    with open(os.path.join(config.SCREENSHOT_DIR, filename), "wb") as fh:
        fh.write(resp.content)
    log.info("Screenshot saved: %s", filename)
    return jsonify({"status": "success", "filename": filename})


def _finalize_session(*_):
    if _active_session is not None:
        _active_session.finalize()


atexit.register(_finalize_session)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_finalize_session(), os._exit(0)))

    log.info("--- TREADMILL SERVER STARTING ---")
    log.info("Serial: %s @ %d  Model: %s  Interval: %ds  Fake serial/LLM: %s/%s",
             config.SERIAL_PORT, config.SERIAL_BAUD, config.LLM_MODEL,
             config.UPDATE_INTERVAL_SEC, config.FAKE_SERIAL, config.FAKE_LLM)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
