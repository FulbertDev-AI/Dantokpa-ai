
from app.config import PRODUCTS_FILE, load_json


def verifier_stock(product_id: str) -> dict:
    """Vérifie le stock d'un produit à partir de son identifiant."""
    if not isinstance(product_id, str) or not product_id.strip():
        return {
            "success": False,
            "message": "L'identifiant du produit est invalide.",
        }

    products = load_json(PRODUCTS_FILE)

    for product in products:
        if product["id"].upper() == product_id.upper():
            return {
                "success": True,
                "product_id": product["id"],
                "product_name": product["name"],
                "stock": product["stock"],
                "available": product["stock"] > 0
            }

    return {
        "success": False,
        "message": f"Aucun produit trouvé avec l'identifiant {product_id}."
    }
