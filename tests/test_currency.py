
from app.tools import currency


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "date": "2026-11-02",
            "base": "XOF",
            "quote": "EUR",
            "rate": 0.001524
        }


def test_currency_conversion_success(monkeypatch):
    monkeypatch.setattr(
        currency.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse()
    )

    result = currency.convertir_devise(12000, "EUR")

    assert result["success"] is True
    assert result["converted_amount"] == 18.29
    assert result["target_currency"] == "EUR"


def test_unsupported_currency():
    result = currency.convertir_devise(12000, "USD")

    assert result["success"] is False


def test_invalid_amount():
    result = currency.convertir_devise(-100, "EUR")

    assert result["success"] is False
