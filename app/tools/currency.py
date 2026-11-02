
from decimal import Decimal, ROUND_HALF_UP
import math

import httpx


from app.config import FRANKFURTER_API_URL

API_URL = FRANKFURTER_API_URL

SUPPORTED_CURRENCIES = {
    "EUR": "Euro",
    "NGN": "Naira nigérian",
}


def convertir_devise(
    amount: float,
    target_currency: str
) -> dict:
    """
    Convertit un montant en FCFA vers EUR ou NGN
    en utilisant le taux de change fourni par Frankfurter.
    """

    try:
        valid_amount = (
            not isinstance(amount, bool)
            and isinstance(amount, (int, float, Decimal))
            and math.isfinite(float(amount))
            and amount > 0
        )
    except (OverflowError, TypeError, ValueError):
        valid_amount = False

    if not valid_amount:
        return {
            "success": False,
            "message": "Le montant doit être supérieur à zéro."
        }

    target = target_currency.upper().strip()

    if target not in SUPPORTED_CURRENCIES:
        return {
            "success": False,
            "message": "Devise non prise en charge. Utilisez EUR ou NGN."
        }

    try:
        response = httpx.get(
            f"{API_URL}/XOF/{target}",
            timeout=10.0
        )
        response.raise_for_status()

        data = response.json()
        rate = Decimal(str(data["rate"]))
        converted_amount = (
            Decimal(str(amount)) * rate
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "success": True,
            "original_amount": amount,
            "original_currency": "XOF",
            "converted_amount": float(converted_amount),
            "target_currency": target,
            "rate": float(rate),
            "rate_date": data["date"],
            "source": "Frankfurter"
        }

    except (httpx.HTTPError, KeyError, ValueError) as error:
        return {
            "success": False,
            "message": "Impossible de récupérer le taux de change actuellement.",
            "error": str(error)
        }
