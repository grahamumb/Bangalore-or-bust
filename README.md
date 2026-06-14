# Bangalore-or-bust

Turn a walking treadmill into a virtual walk across a country. As you walk, a
Raspberry Pi advances your position along a GPX route and shows the matching
Google Street View, slowly panning between updates.

## How it works

```
 Treadmill console ──photos──> ESP32-CAM ──UART──> Raspberry Pi ──> Claude Haiku 4.5
                                                        │                   │
                                                        │   speed/distance/time (JSON)
                                                        ▼
                                            position along route.gpx
                                                        ▼
                                  Google Street View + mini-map + town facts
```

Every `UPDATE_INTERVAL_SEC` (default 60s) the Pi asks the ESP32-CAM for **4
photos taken 5s apart** of the treadmill console. The console cycles through its
metrics (time / distance / calories / speed), so 4 photos catch the full cycle.
Claude Haiku 4.5 reads the photos and returns speed, distance, time, and
calories as strict JSON. Position is driven by the **LLM-reported distance**:

```
total_distance = cumulative_distance (persisted) + this session's distance
```

So your position survives restarts, and each session's stats are logged.

## Hardware

- Raspberry Pi 4
- ESP32-CAM (AI-Thinker), pointed at the treadmill console
- A UART link between them (Pi `/dev/serial0` TX/RX ↔ ESP32 RX/TX, common GND),
  or a USB-serial adapter (`/dev/ttyUSB0`)

Flash `esp32/treadmill_cam/treadmill_cam.ino` with the Arduino IDE
("AI Thinker ESP32-CAM" board).

## Setup (Pi)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys/port
python treadmill.py
```

Open `http://<pi-ip>:5000`. Click 📷 SCREENSHOT to save the current Street View
(via the Street View Static API) into `screenshots/`.

`.env` needs an `ANTHROPIC_API_KEY` and a `GOOGLE_MAPS_API_KEY` with the Maps
JavaScript, Street View Static, and Geocoding APIs enabled. See `.env.example`.

## Develop without hardware

```bash
FAKE_SERIAL=1 FAKE_LLM=1 UPDATE_INTERVAL_SEC=2 \
  GOOGLE_MAPS_API_KEY=yourkey python treadmill.py
```

`FAKE_SERIAL` reads the placeholder JPEGs in `samples/` instead of the ESP32;
`FAKE_LLM` returns canned readings instead of calling Anthropic. The full loop,
persistence, mini-map, and town HUD all work. (A Maps key is still needed for
the browser to render Street View.)

Run the tests:

```bash
python -m pytest tests/
```

## Files

| File | Role |
|------|------|
| `treadmill.py` | Flask server + background capture/read/position loop |
| `camera_serial.py` | UART protocol with the ESP32-CAM |
| `llm.py` | Claude Haiku 4.5: read display, town facts |
| `geocode.py` | Reverse-geocode position → town/region |
| `state.py` | Persist cumulative distance + per-session stats |
| `config.py` | Env-based configuration (+ tiny `.env` loader) |
| `templates/index.html` | Street View, mini-map, HUD, town info |
| `esp32/treadmill_cam/` | ESP32-CAM firmware |
