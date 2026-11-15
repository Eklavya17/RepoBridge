"""Old pricing code kept for reference. Not called anywhere (a retrieval decoy)."""


def apply_rate_legacy(amount, rate=None):
    # apply_rate used to treat a missing rate (None) as "no discount"
    if rate is None:
        return amount
    return amount * (1 - rate)
