import time
import os
import base64
from datetime import datetime
from flask import Flask, jsonify, render_template
from gpiozero import Button
import gpxpy
import gpxpy.gpx
from geopy.distance import geodesic

app = Flask(__name__)

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), 'screenshots')
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

# --- CONFIGURATION ---
ROLLER_CIRCUMFERENCE = 0.157  # Standard for 50mm roller
GPX_FILE = 'route.gpx'
GPIO_PIN = 14
TIMEOUT = 2.0                 

# --- STATE ---
current_stats = {
    "speed": 0.0,
    "lat": 0.0,
    "lng": 0.0,
    "distance_travelled": 0.0
}

last_pulse_time = time.time()
path_coords = []

# Load GPX Path
try:
    with open(GPX_FILE, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    path_coords.append((point.latitude, point.longitude))
except FileNotFoundError:
    print(f"!!! WARNING: {GPX_FILE} not found. Defaulting to Chicago coords.")
    path_coords = [(41.8781, -87.6298), (41.8788, -87.6359)]

def calculate_position(distance_m):
    accumulated_dist = 0.0
    for i in range(len(path_coords) - 1):
        p1 = path_coords[i]
        p2 = path_coords[i+1]
        segment_dist = geodesic(p1, p2).meters
        
        if accumulated_dist + segment_dist >= distance_m:
            over_dist = distance_m - accumulated_dist
            ratio = over_dist / segment_dist
            lat = p1[0] + (p2[0] - p1[0]) * ratio
            lng = p1[1] + (p2[1] - p1[1]) * ratio
            return lat, lng
        
        accumulated_dist += segment_dist
    return path_coords[-1]

def on_magnet_pass():
    global last_pulse_time
    now = time.time()
    dt = now - last_pulse_time
    
    # Software debounce (ignore pulses faster than 25km/h)
    if dt > 0.02: 
        current_stats["speed"] = ROLLER_CIRCUMFERENCE / dt
        current_stats["distance_travelled"] += ROLLER_CIRCUMFERENCE
        
        new_lat, new_lng = calculate_position(current_stats["distance_travelled"])
        current_stats["lat"] = new_lat
        current_stats["lng"] = new_lng
        
        # --- TERMINAL DEBUGGING ---
        print(f"磁 [MAGNET DETECTED] | Speed: {current_stats['speed']:.2f} m/s | Total Dist: {current_stats['distance_travelled']:.2f} m")
        
        last_pulse_time = now

@app.route('/save_screenshot', methods=['POST'])
def save_screenshot():
    import json
    from flask import request
    
    data = request.json
    img_data = data.get('image').split(',')[1] # Remove the "data:image/png;base64," header
    
    filename = f"walk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    
    with open(filepath, "wb") as fh:
        fh.write(base64.b64decode(img_data))
    
    print(f"📸 Screenshot saved: {filename}")
    return jsonify({"status": "success", "filename": filename})
# Hardware Setup
# IMPORTANT: If your resistor is actually 10,000 kOhm (10 Megaohm), 
# this might not trigger reliably. Try a 10 kOhm resistor if it fails.
sensor = Button(GPIO_PIN, pull_up=False) 
sensor.when_pressed = on_magnet_pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    if time.time() - last_pulse_time > TIMEOUT:
        current_stats["speed"] = 0.0
    return jsonify(current_stats)

if __name__ == '__main__':
    current_stats["lat"], current_stats["lng"] = path_coords[0]
    print("--- TREADMILL SERVER STARTED ---")
    print(f"Monitoring GPIO Pin: {GPIO_PIN}")
    print("Waiting for magnet pulses...")
    app.run(host='0.0.0.0', port=5000, debug=False)
