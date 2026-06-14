"""Reverse-geocode a lat/lng to a town + region using the Google Geocoding API."""
import logging

import requests

import config

log = logging.getLogger("geocode")

_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def _component(components, *types):
    for comp in components:
        if any(t in comp.get("types", []) for t in types):
            return comp.get("long_name")
    return None


def reverse_geocode(lat, lng):
    """Return (town, region) for a coordinate, or (None, None) on failure."""
    if config.FAKE_LLM or not config.GOOGLE_MAPS_API_KEY:
        # In dev mode, synthesize a stable-ish town name from the coordinate.
        return (f"Town {round(lat, 2)},{round(lng, 2)}", "Demo Region")
    try:
        resp = requests.get(
            _URL,
            params={"latlng": f"{lat},{lng}", "key": config.GOOGLE_MAPS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return (None, None)
        components = results[0].get("address_components", [])
        town = _component(components, "locality", "postal_town", "administrative_area_level_3")
        region = _component(components, "administrative_area_level_1", "country")
        return (town, region)
    except (requests.RequestException, ValueError) as exc:
        log.warning("reverse geocode failed: %s", exc)
        return (None, None)
