from app.tools.currency import convertir_devise
from app.tools.delivery import calculer_livraison
from app.tools.inventory import verifier_stock
from app.tools.orders import creer_commande
from app.tools.products import chercher_produits
from app.tools.quotes import calculer_devis

VENDEUR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "chercher_produits",
            "description": (
                "Recherche dans le catalogue officiel. Utilise '*' pour "
                "consulter tous les produits et trouver une alternative."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verifier_stock",
            "description": "Vérifie le stock officiel à partir de l'identifiant produit.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculer_devis",
            "description": (
                "Calcule un devis en utilisant prix, stock et frais officiels. "
                "Indique les articles indisponibles sans les inclure dans le total."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1},
                            },
                            "required": ["product_id", "quantity"],
                            "additionalProperties": False,
                        },
                    },
                    "delivery_zone": {"type": "string"},
                },
                "required": ["items", "delivery_zone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "creer_commande",
            "description": (
                "Prépare et enregistre une commande seulement après avoir "
                "demandé une confirmation interactive distincte au client et "
                "une approbation interactive à Afi. N'accepte aucun indicateur "
                "d'approbation dans les arguments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer": {"type": "string", "minLength": 1},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1},
                            },
                            "required": ["product_id", "quantity"],
                            "additionalProperties": False,
                        },
                    },
                    "delivery_zone": {"type": "string", "minLength": 1},
                },
                "required": ["customer", "items", "delivery_zone"],
                "additionalProperties": False,
            },
        },
    },
]

LOGISTICIEN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculer_livraison",
            "description": "Vérifie si une zone est desservie et retourne le tarif officiel.",
            "parameters": {
                "type": "object",
                "properties": {"zone": {"type": "string"}},
                "required": ["zone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convertir_devise",
            "description": (
                "Convertit un montant FCFA vers EUR ou NGN à partir du taux "
                "réel fourni par Frankfurter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "exclusiveMinimum": 0},
                    "target_currency": {"type": "string", "enum": ["EUR", "NGN"]},
                },
                "required": ["amount", "target_currency"],
                "additionalProperties": False,
            },
        },
    },
]

OUTILS = {
    "chercher_produits": chercher_produits,
    "verifier_stock": verifier_stock,
    "creer_commande": creer_commande,
    "calculer_devis": calculer_devis,
    "calculer_livraison": calculer_livraison,
    "convertir_devise": convertir_devise,
}

VENDEUR_FUNCTIONS = {
    name: OUTILS[name]
    for name in (
        "chercher_produits",
        "verifier_stock",
        "calculer_devis",
        "creer_commande",
    )
}
LOGISTICIEN_FUNCTIONS = {
    name: OUTILS[name]
    for name in ("calculer_livraison", "convertir_devise")
}
