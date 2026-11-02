
from datetime import datetime, timezone
import logging
from threading import RLock
from uuid import uuid4

from app.config import (
    PRODUCTS_FILE,
    ORDERS_FILE,
    load_json,
    save_json
)
from app.services.approval import (
    demander_approbation_humaine,
    demander_confirmation_client,
)
from app.tools.quotes import calculer_devis

logger = logging.getLogger(__name__)
_ORDER_LOCK = RLock()


def creer_commande(
    customer: str,
    items: list[dict],
    delivery_zone: str
) -> dict:
    """
    Demande confirmation au client et approbation interactive à Afi,
    puis enregistre la commande sans exposer de booléen d'approbation.

    items = [
        {"product_id": "P05", "quantity": 2}
    ]
    """
    if not isinstance(customer, str) or not customer.strip():
        return {"success": False, "message": "Le nom du client est invalide."}
    if not isinstance(delivery_zone, str) or not delivery_zone.strip():
        return {"success": False, "message": "La zone de livraison est invalide."}
    if not isinstance(items, list) or not items:
        return {
            "success": False,
            "message": "La commande ne contient aucun article."
        }

    with _ORDER_LOCK:
        return _creer_commande_verifiee(customer.strip(), items, delivery_zone.strip())


def _creer_commande_verifiee(
    customer: str,
    items: list[dict],
    delivery_zone: str,
) -> dict:
    try:
        quote = calculer_devis(items, delivery_zone)
        if not quote["success"]:
            return quote
        if not quote["available_items"]:
            return {
                "success": False,
                "message": "Aucun article demandé n'est disponible en stock.",
                "unavailable_items": quote["unavailable_items"],
            }
        products = load_json(PRODUCTS_FILE)
        orders = load_json(ORDERS_FILE)
    except (OSError, TypeError, ValueError) as error:
        logger.exception("Impossible de lire le stockage des commandes.")
        return {
            "success": False,
            "message": "Impossible de lire le stockage des commandes.",
            "error": str(error),
        }

    products_by_id = {product["id"]: product for product in products}
    requested_ids = {
        str(item["product_id"]).upper() for item in items
    }
    requested_quantities = {
        item["product_id"]: item["quantity"]
        for item in quote["available_items"]
    }
    order_items = []
    for quoted_item in quote["available_items"]:
        product = products_by_id.get(quoted_item["product_id"])
        if (
            product is None
            or product["price"] != quoted_item["unit_price"]
            or product["stock"] < quoted_item["quantity"]
        ):
            return {
                "success": False,
                "message": (
                    "Le catalogue a changé pendant le calcul du devis. "
                    "Veuillez recommencer."
                ),
                "stage": "revalidation",
            }
        order_items.append(
            {
                "product_id": product["id"],
                "product_name": product["name"],
                "unit_price": product["price"],
                "quantity": quoted_item["quantity"],
                "line_total": quoted_item["line_total"],
            }
        )

    alternative = next(
        (
            {
                "product_id": product["id"],
                "product_name": product["name"],
                "price": product["price"],
                "stock": product["stock"],
            }
            for product in products
            if product["stock"] > 0 and product["id"] not in requested_ids
        ),
        None,
    )

    order = {
        "order_id": str(uuid4()),
        "customer": customer,
        "items": order_items,
        "unavailable_items": quote["unavailable_items"],
        "delivery_zone": delivery_zone,
        "subtotal": quote["subtotal"],
        "delivery_fee": quote["delivery_fee"],
        "total": quote["total"],
        "currency": "XOF",
        "status": "pending_approval",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    if alternative is not None:
        order["suggested_alternative"] = alternative

    if not demander_confirmation_client(order):
        return {
            "success": False,
            "message": "Le client n'a pas confirmé la commande.",
            "stage": "customer_confirmation",
        }

    if not demander_approbation_humaine(order):
        return {
            "success": False,
            "message": "La commande n'a pas été approuvée par Afi.",
            "stage": "afi_approval",
        }

    # Recheck the stock after interactive approvals.
    try:
        current_products = load_json(PRODUCTS_FILE)
    except (OSError, TypeError, ValueError) as error:
        logger.exception("Impossible de relire le stock après approbation.")
        return {
            "success": False,
            "message": "Impossible de relire le stock après approbation.",
            "error": str(error),
        }
    current_by_id = {product["id"]: product for product in current_products}
    for product_id, quantity in requested_quantities.items():
        current_product = current_by_id.get(product_id)
        quoted_product = products_by_id[product_id]
        if (
            current_product is None
            or current_product["stock"] < quantity
            or current_product["price"] != quoted_product["price"]
        ):
            return {
                "success": False,
                "message": (
                    "Le stock ou le prix a changé pendant la validation. "
                    "Veuillez préparer un nouveau récapitulatif."
                ),
                "stage": "revalidation",
            }

    for product_id, quantity in requested_quantities.items():
        current_by_id[product_id]["stock"] -= quantity

    order["status"] = "approved"
    try:
        save_json(ORDERS_FILE, [*orders, order])
        try:
            save_json(PRODUCTS_FILE, current_products)
        except (OSError, TypeError, ValueError):
            try:
                save_json(ORDERS_FILE, orders)
            except (OSError, TypeError, ValueError) as rollback_error:
                logger.exception("Échec du rollback après erreur de stockage.")
                return {
                    "success": False,
                    "message": (
                        "Erreur critique : la commande a été écrite mais "
                        "le rollback du fichier de commandes a échoué."
                    ),
                    "error": str(rollback_error),
                }
            raise
    except (OSError, TypeError, ValueError) as error:
        logger.exception("Impossible de sauvegarder la commande.")
        return {
            "success": False,
            "message": "Impossible de sauvegarder la commande.",
            "error": str(error),
        }

    return {
        "success": True,
        "message": "Commande enregistrée avec succès.",
        "order": order
    }
