"""Checkout entry point."""

import shop.pricing as pricing


def run_checkout(items, settings_text):
    total = pricing.total_price(items, settings_text)
    return {"total": total, "items": len(items)}
