"""Talk to the ESP32-CAM over UART.

Protocol (see esp32/treadmill_cam/treadmill_cam.ino):
    Pi  -> ESP32:  "CAPTURE\n"
    ESP32 -> Pi :  for each of 4 frames:
                       "IMG <index> <byte_length>\n"
                       <byte_length> raw JPEG bytes
                   "DONE\n"

capture_frames() returns a list of JPEG byte strings (normally 4).
With config.FAKE_SERIAL set, it reads sample JPEGs from samples/ instead so
the whole pipeline can run without hardware.
"""
import glob
import os
import time

import config

CAPTURE_CMD = b"CAPTURE\n"
# 4 frames * 5s apart, plus encode/transfer headroom.
CAPTURE_TIMEOUT_S = 40


def _fake_frames():
    paths = sorted(glob.glob(os.path.join(config.SAMPLES_DIR, "*.jpg")))
    paths += sorted(glob.glob(os.path.join(config.SAMPLES_DIR, "*.jpeg")))
    frames = []
    for p in paths[:4]:
        with open(p, "rb") as fh:
            frames.append(fh.read())
    return frames


def _read_line(ser):
    return ser.readline().decode("ascii", errors="replace").strip()


def _read_exact(ser, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if not chunk:
            raise TimeoutError("serial read timed out mid-frame")
        buf.extend(chunk)
    return bytes(buf)


def capture_frames():
    """Request a capture and return a list of JPEG byte strings."""
    if config.FAKE_SERIAL:
        return _fake_frames()

    import serial  # imported lazily so dev machines don't need pyserial+hardware

    with serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUD, timeout=2) as ser:
        ser.reset_input_buffer()
        ser.write(CAPTURE_CMD)
        ser.flush()

        frames = []
        deadline = time.monotonic() + CAPTURE_TIMEOUT_S
        while time.monotonic() < deadline:
            line = _read_line(ser)
            if not line:
                continue
            if line == "DONE":
                break
            if line.startswith("IMG"):
                parts = line.split()
                if len(parts) != 3:
                    continue
                length = int(parts[2])
                frames.append(_read_exact(ser, length))
        return frames
