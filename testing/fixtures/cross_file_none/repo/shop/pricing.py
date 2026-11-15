"""Price computation."""

from shop import discount


def subtotal(items):
    return sum(price * qty for price, qty in items)


def apply_rate(amount, rate):
    return round(amount * (1 - rate), 2)


def total_price(items, settings_text):
    rate = discount.resolve_rate(settings_text)
    amount = subtotal(items)
    return apply_rate(amount, rate)


class PriceEngine:
    def __init__(self, settings_text):
        self.settings_text = settings_text
        self.policy = discount.SeasonalPolicy()

    def quote(self, items):
        return total_price(items, self.settings_text)

    def quote_with_hooks(self, items, hooks):
        result = self.quote(items)
        for hook in hooks:
            result = hook(result)
        return result
