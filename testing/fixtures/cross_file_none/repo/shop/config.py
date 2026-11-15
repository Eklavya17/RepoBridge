"""Settings parsing."""

import json


def parse(text):
    if not text.strip():
        return {}
    return json.loads(text)


def load(text):
    settings = parse(text)
    return settings
