"""Discount lookup."""

from .config import load


class BasePolicy:
    def default_rate(self):
        return 0.0


class SeasonalPolicy(BasePolicy):
    def rate_for(self, settings):
        if "season" in settings:
            return settings["season"]
        return self.default_rate()


def lookup_rate(settings):
    return settings.get("discount")


def resolve_rate(settings_text):
    settings = load(settings_text)
    rate = lookup_rate(settings)
    return rate
