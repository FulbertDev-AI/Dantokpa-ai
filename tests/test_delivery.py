
from app.tools.delivery import calculer_livraison


def test_calavi_delivery():
    result = calculer_livraison("Calavi")

    assert result["success"] is True
    assert result["fee"] == 2000


def test_porto_novo_delivery():
    result = calculer_livraison("Porto-Novo")

    assert result["success"] is True
    assert result["fee"] == 3000


def test_unsupported_delivery_zone():
    result = calculer_livraison("Lomé")

    assert result["success"] is False
    assert result["supported"] is False


def test_delivery_with_accent():
    result = calculer_livraison("Fidjrossè")

    assert result["success"] is True
    assert result["fee"] == 1500
