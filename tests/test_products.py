
from app.tools.products import chercher_produits
from app.tools.inventory import verifier_stock


def test_search_existing_product():
    result = chercher_produits("pagne")

    assert result["success"] is True
    assert result["count"] >= 1
    assert result["products"][0]["id"] == "P01"


def test_search_multiple_products():
    result = chercher_produits("wax")

    product_ids = [product["id"] for product in result["products"]]

    assert "P01" in product_ids
    assert "P05" in product_ids


def test_out_of_stock_product():
    result = verifier_stock("P03")

    assert result["success"] is True
    assert result["stock"] == 0
    assert result["available"] is False


def test_unknown_product():
    result = verifier_stock("P99")

    assert result["success"] is False


def test_search_catalog_for_alternatives():
    result = chercher_produits("*")

    assert result["success"] is True
    assert result["count"] == 6
    assert any(product["stock"] > 0 for product in result["products"])
