from app.config import PRODUCTS_FILE, load_json
from app.tools.delivery import calculer_livraison


def calculer_devis(items: list[dict], delivery_zone: str) -> dict:
    """Calcule un devis depuis le catalogue, le stock et les tarifs officiels."""
    if not isinstance(items, list) or not items:
        return {"success": False, "message": "Le devis ne contient aucun article."}
    if not isinstance(delivery_zone, str) or not delivery_zone.strip():
        return {"success": False, "message": "La zone de livraison est invalide."}

    quantities: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            return {"success": False, "message": "Un article est invalide."}
        product_id = str(item.get("product_id", "")).strip().upper()
        quantity = item.get("quantity")
        if (
            not product_id
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return {
                "success": False,
                "message": "Un article ou une quantité est invalide.",
            }
        quantities[product_id] = quantities.get(product_id, 0) + quantity

    products = load_json(PRODUCTS_FILE)
    products_by_id = {product["id"].upper(): product for product in products}
    available_items = []
    unavailable_items = []
    subtotal = 0

    for product_id, quantity in quantities.items():
        product = products_by_id.get(product_id)
        if product is None:
            return {
                "success": False,
                "message": f"Produit introuvable : {product_id}.",
            }
        line = {
            "product_id": product["id"],
            "product_name": product["name"],
            "unit_price": product["price"],
            "quantity": quantity,
            "stock": product["stock"],
        }
        if product["stock"] < quantity:
            unavailable_items.append(line)
            continue
        line["line_total"] = product["price"] * quantity
        available_items.append(line)
        subtotal += line["line_total"]

    delivery = calculer_livraison(delivery_zone)
    if not delivery["success"]:
        return delivery

    return {
        "success": True,
        "available_items": available_items,
        "unavailable_items": unavailable_items,
        "subtotal": subtotal,
        "delivery_fee": delivery["fee"],
        "total": subtotal + delivery["fee"],
        "delivery_zone": delivery_zone,
        "delivery_time": delivery["delivery_time"],
        "currency": "XOF",
    }
