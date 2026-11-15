from shop.checkout import run_checkout
from shop.pricing import PriceEngine


def test_checkout_without_discount():
    run_checkout([(10.0, 2)], '{"currency": "EUR"}')


def test_checkout_with_discount():
    assert run_checkout([(10.0, 2)], '{"discount": 0.5}')["total"] == 10.0


class TestEngine:
    def test_quote(self):
        assert PriceEngine('{"discount": 0.0}').quote([(1.0, 1)]) == 1.0
