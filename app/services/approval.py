
import getpass
import hmac
import os


def _demander_confirmation(prompt: str) -> bool:
    try:
        choice = input(prompt).strip().casefold()
    except EOFError:
        print("Aucune confirmation reçue.")
        return False
    return choice in {"o", "oui"}


def demander_confirmation_client(order_summary: dict) -> bool:
    """Demande au client une confirmation explicite du récapitulatif."""
    print("\n========== CONFIRMATION CLIENT ==========")
    print(f"Client : {order_summary['customer']}")
    print(f"Articles : {order_summary['items']}")
    print(f"Sous-total : {order_summary['subtotal']} FCFA")
    print(f"Livraison : {order_summary['delivery_fee']} FCFA")
    print(f"TOTAL : {order_summary['total']} FCFA")
    print(f"Destination : {order_summary['delivery_zone']}")
    if order_summary.get("unavailable_items"):
        print(
            "Articles indisponibles (non inclus dans la commande) : "
            f"{order_summary['unavailable_items']}"
        )
        alternative = order_summary.get("suggested_alternative")
        if alternative:
            print(f"Alternative disponible du catalogue : {alternative}")

    prompt = (
        "Confirmez-vous uniquement les articles disponibles ? [o/N] : "
        if order_summary.get("unavailable_items")
        else "Confirmez-vous cette commande ? [o/N] : "
    )
    confirmed = _demander_confirmation(prompt)
    print(
        "Confirmation du client reçue."
        if confirmed
        else "Commande non confirmée par le client."
    )
    return confirmed


def demander_approbation_humaine(order_summary: dict) -> bool:
    """
    Demande l'approbation interactive d'Afi.

    Cette fonction n'accepte aucun indicateur d'approbation fourni par l'agent.
    Le code confidentiel d'Afi est configuré hors du code et saisi à l'aveugle.
    """
    print("\n========== VALIDATION DE COMMANDE ==========")
    print(f"Client : {order_summary['customer']}")
    print(f"Articles : {order_summary['items']}")
    print(f"Sous-total : {order_summary['subtotal']} FCFA")
    print(f"Livraison : {order_summary['delivery_fee']} FCFA")
    print(f"TOTAL : {order_summary['total']} FCFA")
    print(f"Destination : {order_summary['delivery_zone']}")
    if order_summary.get("unavailable_items"):
        print(
            "Articles indisponibles (non inclus) : "
            f"{order_summary['unavailable_items']}"
        )
        if order_summary.get("suggested_alternative"):
            print(
                "Alternative disponible du catalogue : "
                f"{order_summary['suggested_alternative']}"
            )

    approval_code = os.getenv("AFI_APPROVAL_CODE", "")
    if not approval_code:
        print(
            "Approbation refusée : AFI_APPROVAL_CODE n'est pas configuré."
        )
        return False

    try:
        submitted_code = getpass.getpass(
            "\nAfi, saisissez votre code confidentiel pour approuver : "
        )
    except EOFError:
        print("Aucun code d'approbation reçu.")
        return False

    approved = hmac.compare_digest(submitted_code, approval_code)
    if approved:
        print("Approbation accordée.")
    else:
        print("Code invalide : commande non approuvée.")

    return approved
