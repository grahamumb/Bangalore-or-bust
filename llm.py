"""Claude Haiku 4.5 calls: read the treadmill display from photos, and
generate facts about a town we've just entered.

Both use strict JSON via output_config.format so the response is guaranteed
to parse against our schema.
"""
import base64
import json
import logging

import config

log = logging.getLogger("llm")

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None)
    return _client


# The treadmill cycles its display through the four metrics; a lit icon next to
# one of the corner words marks which metric the big number currently shows.
# Corner layout: time=upper-left, distance=upper-right, calories=bottom-right,
# speed=bottom-left. Four photos 5s apart capture the whole cycle.
_DISPLAY_PROMPT = """\
These are 4 photos of a treadmill console, taken 5 seconds apart.

The console cycles through four metrics. A small lit icon next to one of the \
corner labels indicates which metric the large central number currently shows. \
The corner labels are: TIME (upper-left), DISTANCE (upper-right), \
CALORIES (bottom-right), SPEED (bottom-left).

Across the 4 photos, read whichever metric is active in each, and combine them \
into a single best reading. Distance is in miles. Speed is in miles per hour. \
Time is the elapsed workout time; report it as total minutes (e.g. 12.5). \
If a value can't be read in any photo, use null. Return only the JSON.
"""

_DISPLAY_SCHEMA = {
    "type": "object",
    "properties": {
        "speed_mph": {"type": ["number", "null"]},
        "distance_mi": {"type": ["number", "null"]},
        "time_minutes": {"type": ["number", "null"]},
        "calories": {"type": ["number", "null"]},
    },
    "required": ["speed_mph", "distance_mi", "time_minutes", "calories"],
    "additionalProperties": False,
}

_TOWN_SCHEMA = {
    "type": "object",
    "properties": {
        "population": {"type": ["string", "null"]},
        "fun_fact": {"type": ["string", "null"]},
        "famous_person": {"type": ["string", "null"]},
    },
    "required": ["population", "fun_fact", "famous_person"],
    "additionalProperties": False,
}


def _first_json(response):
    for block in response.content:
        if block.type == "text":
            return json.loads(block.text)
    raise ValueError("no text block in LLM response")


def read_display(jpegs):
    """Return {speed_mph, distance_mi, time_minutes, calories} from 4 JPEGs."""
    if config.FAKE_LLM:
        return {"speed_mph": 3.0, "distance_mi": 0.05, "time_minutes": 1.0, "calories": 5}

    content = []
    for jpeg in jpegs:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(jpeg).decode("ascii"),
            },
        })
    content.append({"type": "text", "text": _DISPLAY_PROMPT})

    response = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": _DISPLAY_SCHEMA}},
    )
    return _first_json(response)


def town_facts(town, region):
    """Return {population, fun_fact, famous_person} for a town (one call per town)."""
    if config.FAKE_LLM:
        return {
            "population": "~10,000",
            "fun_fact": f"{town} has a surprisingly large number of roundabouts.",
            "famous_person": "A locally beloved cheesemaker.",
        }

    prompt = (
        f"Give brief facts about the town of {town}"
        + (f", {region}" if region else "")
        + ". population is an approximate string like '12,000'. "
        "fun_fact is one sentence. famous_person is one notable person born or "
        "strongly associated with the town (name + a few words). Use null if unknown."
    )
    response = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _TOWN_SCHEMA}},
    )
    return _first_json(response)
