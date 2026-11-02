
import unicodedata

from app.config import PRODUCTS_FILE, load_json


def normalize_text(value: str) -> str:
    """Normalise le texte pour faciliter les recherches."""
    value = unicodedata.normalize("NFD", value.lower())
    return "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )


def chercher_produits(query: str) -> dict:
    """
    Recherche des produits dans le catalogue.
    Les produits indisponibles restent visibles dans les résultats.
    """
    if not isinstance(query, str) or not query.strip():
        return {
            "success": False,
            "message": "Précisez le produit recherché, ou utilisez '*' pour le catalogue.",
            "products": []
        }

    products = load_json(PRODUCTS_FILE)
    normalized_query = normalize_text(query)

    if normalized_query in {"*", "catalogue", "catalog"}:
        return {
            "success": True,
            "count": len(products),
            "products": products,
        }

    matching_products = []

    for product in products:
        normalized_name = normalize_text(product["name"])
        normalized_description = normalize_text(product["description"])

        if (
            normalized_query in normalized_name
            or normalized_query in normalized_description
            or all(
                word in normalized_name
                for word in normalized_query.split()
            )
        ):
            matching_products.append(product)

    return {
        "success": True,
        "count": len(matching_products),
        "products": matching_products
    }
