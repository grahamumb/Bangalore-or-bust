import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import treadmill


def test_start_of_path():
    coords = [(0.0, 0.0), (0.0, 1.0)]
    assert treadmill.interpolate_position(coords, 0.0) == (0.0, 0.0)


def test_past_end_returns_last_point():
    coords = [(0.0, 0.0), (0.0, 0.001)]
    assert treadmill.interpolate_position(coords, 1_000_000) == (0.0, 0.001)


def test_midpoint_interpolation():
    # Two points ~111 m apart in latitude; halfway should be ~half the lat.
    coords = [(0.0, 0.0), (0.001, 0.0)]
    from geopy.distance import geodesic
    total = geodesic(coords[0], coords[1]).meters
    lat, lng = treadmill.interpolate_position(coords, total / 2)
    assert abs(lat - 0.0005) < 1e-6
    assert abs(lng) < 1e-9


def test_miles_to_meters():
    assert abs(config.meters_from_distance(1.0) - 1609.344) < 1e-6
    assert config.meters_from_distance(None) == 0.0
