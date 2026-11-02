import json

from app.tools import quotes


def prepare_products(tmp_path, monkeypatch):
    products_file = tmp_path / "products.json"
    products_file.write_text(
        json.dumps(
            [
                {
                    "id": "P05",
                    "name": "Robe en wax",
                    "price": 22000,
                    "stock": 5,
                    "description": "Robe en wax.",
                },
                {
                    "id": "P03",
                    "name": "Sac en raphia",
                    "price": 7500,
                    "stock": 0,
                    "description": "Sac en raphia.",
                },
                {
                    "id": "P06",
                    "name": "Beurre de karité 500 g",
                    "price": 3500,
                    "stock": 40,
                    "description": "Beurre de karité.",
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(quotes, "PRODUCTS_FILE", products_file)


def test_quote_excludes_out_of_stock_items(tmp_path, monkeypatch):
    prepare_products(tmp_path, monkeypatch)

    result = quotes.calculer_devis(
        [
            {"product_id": "P05", "quantity": 2},
            {"product_id": "P03", "quantity": 1},
        ],
        "Calavi",
    )

    assert result["success"] is True
    assert result["subtotal"] == 44000
    assert result["delivery_fee"] == 2000
    assert result["total"] == 46000
    assert [item["product_id"] for item in result["unavailable_items"]] == ["P03"]


def test_quote_calculates_karite_delivery(tmp_path, monkeypatch):
    prepare_products(tmp_path, monkeypatch)

    result = quotes.calculer_devis(
        [{"product_id": "P06", "quantity": 3}],
        "Porto-Novo",
    )

    assert result["success"] is True
    assert result["total"] == 13500


def test_quote_rejects_invalid_quantity(tmp_path, monkeypatch):
    prepare_products(tmp_path, monkeypatch)

    result = quotes.calculer_devis(
        [{"product_id": "P06", "quantity": True}],
        "Porto-Novo",
    )

    assert result["success"] is False
