
DELIVERY_ZONES = {
    "cotonou": 1000,
    "akpakpa": 1000,
    "fidjrosse": 1500,
    "calavi": 2000,
    "porto-novo": 3000,
    "ouidah": 3500
}

DELIVERY_TIME = "24 à 48 heures"


def normalize_zone(zone: str) -> str:
    import unicodedata

    if not isinstance(zone, str):
        return ""
    normalized = unicodedata.normalize("NFD", zone.lower().strip())
    normalized = "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    )
    return normalized


def calculer_livraison(zone: str) -> dict:
    """Retourne les frais et le délai d'une zone desservie."""

    normalized_zone = normalize_zone(zone)

    if normalized_zone not in DELIVERY_ZONES:
        return {
            "success": False,
            "supported": False,
            "message": f"La livraison n'est pas disponible à {zone}.",
            "available_zones": list(DELIVERY_ZONES.keys())
        }

    return {
        "success": True,
        "supported": True,
        "zone": zone,
        "fee": DELIVERY_ZONES[normalized_zone],
        "currency": "XOF",
        "delivery_time": DELIVERY_TIME
    }
