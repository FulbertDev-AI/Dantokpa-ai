import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.tools.products import normalize_text


_MONEY = re.compile(
    r"(?<!\w)(\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,8})?)\s*"
    r"(FCFA|XOF|EUR|€|NGN|euros?|nairas?)"
    r"(?=$|[\s.,!?;:])",
    re.IGNORECASE,
)
_TOTAL = re.compile(
    r"(?:total|au total|co[uû]t global)\s*(?:(?:est\s+)?de|:|=)?\s*"
    r"(\d[\d\s\u00a0\u202f]*(?:[.,]\d{1,8})?)\s*"
    r"(FCFA|XOF|EUR|€|NGN|euros?|nairas?)",
    re.IGNORECASE,
)
_OUT_OF_STOCK_WORDS = (
    "rupture",
    "indisponible",
    "plus en stock",
    "épuisé",
    "epuise",
)


def _decimal_amount(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _parse_mentioned_amount(value: str, currency: str) -> Decimal | None:
    compact = value.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if currency.upper() in {"FCFA", "XOF"}:
        compact = compact.replace(".", "").replace(",", "")
    else:
        compact = compact.replace(",", ".")
    return _decimal_amount(compact)


def _currency_code(value: str) -> str:
    normalized = normalize_text(value).casefold()
    if normalized in {"eur", "euro", "euros", "€"}:
        return "EUR"
    if normalized in {"ngn", "naira", "nairas"}:
        return "NGN"
    if normalized in {"fcfa", "xof"}:
        return "XOF"
    return normalized.upper()


def completer_conversion_verifiee(
    answer: str,
    tool_results: list[dict[str, Any]],
) -> str:
    """Include exact exchange facts from API evidence when the writer omits them."""
    for entry in tool_results:
        result = entry.get("result")
        if (
            entry.get("tool") != "convertir_devise"
            or not isinstance(result, dict)
            or not result.get("success")
        ):
            continue
        amount = _decimal_amount(result.get("converted_amount"))
        rate = _decimal_amount(result.get("rate"))
        target = result.get("target_currency")
        rate_date = result.get("rate_date")
        if amount is None or rate is None or not isinstance(target, str):
            continue

        mentioned = [
            _parse_mentioned_amount(match.group(1), match.group(2))
            for match in _MONEY.finditer(answer)
        ]
        if amount not in mentioned:
            amount_text = f"{amount:,.2f}".replace(",", "_").replace(".", ",")
            answer = f"{answer.rstrip()} Conversion : {amount_text.replace('_', ' ')} {target}."

        normalized_answer = normalize_text(answer).casefold()
        rate_text = str(rate)
        if (
            "taux" not in normalized_answer
            or rate_text not in answer
            and rate_text.replace(".", ",") not in answer
        ):
            date_text = (
                f" ({rate_date})"
                if isinstance(rate_date, str) and rate_date not in answer
                else ""
            )
            answer = (
                f"{answer.rstrip()} Taux XOF/{target} : {rate_text}{date_text}."
            )
        elif isinstance(rate_date, str) and rate_date not in answer:
            answer = f"{answer.rstrip()} Date du taux : {rate_date}."
    return answer


def _walk_amounts(value: Any, allowed: set[Decimal], totals: set[Decimal]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "price",
                "fee",
                "subtotal",
                "total",
                "unit_price",
                "line_total",
                "converted_amount",
                "original_amount",
                "rate",
            }:
                amount = _decimal_amount(child)
                if amount is not None:
                    allowed.add(amount)
                    if key == "total":
                        totals.add(amount)
            _walk_amounts(child, allowed, totals)
    elif isinstance(value, list):
        for child in value:
            _walk_amounts(child, allowed, totals)


def _collect_product_evidence(value: Any, products: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if (
            "stock" in value
            and ("product_name" in value or "name" in value)
        ):
            products.append(value)
        for child in value.values():
            _collect_product_evidence(child, products)
    elif isinstance(value, list):
        for child in value:
            _collect_product_evidence(child, products)


def verifier_reponse_code(
    request: str,
    answer: str,
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reject unsupported figures, missing stock warnings, and unsafe length."""
    issues: list[str] = []
    if not answer.strip():
        issues.append("La réponse est vide.")
    if len(answer.split()) >= 80:
        issues.append("La réponse doit contenir moins de 80 mots.")

    allowed_amounts: set[Decimal] = set()
    expected_totals: set[Decimal] = set()
    product_evidence: list[dict[str, Any]] = []
    for entry in tool_results:
        result = entry.get("result")
        _walk_amounts(result, allowed_amounts, expected_totals)
        _collect_product_evidence(result, product_evidence)

    mentioned_amounts: list[Decimal] = []
    mentioned_currency_amounts: set[tuple[Decimal, str]] = set()
    for match in _MONEY.finditer(answer):
        amount = _parse_mentioned_amount(match.group(1), match.group(2))
        context = answer[max(0, match.start() - 50):match.end() + 30]
        is_rate_unit = (
            amount == Decimal("1")
            and match.group(2).upper() in {"FCFA", "XOF"}
            and "taux" in normalize_text(context).casefold()
        )
        if is_rate_unit:
            continue
        if amount is None:
            issues.append("Un montant de la réponse n'a pas pu être vérifié.")
        elif amount not in allowed_amounts:
            issues.append(
                f"Le montant {match.group(1).strip()} {match.group(2)} "
                "n'est pas étayé par les outils."
            )
        if amount is not None:
            mentioned_amounts.append(amount)
            mentioned_currency_amounts.add(
                (amount, _currency_code(match.group(2)))
            )

    if re.search(r"\b(total|co[uû]t global)\b", answer, re.IGNORECASE):
        totals_in_text = [
            _parse_mentioned_amount(match.group(1), match.group(2))
            for match in _TOTAL.finditer(answer)
        ]
        if expected_totals and (
            not totals_in_text
            or any(total not in expected_totals for total in totals_in_text)
        ):
            issues.append("Le total annoncé ne correspond pas au devis vérifié.")
    if expected_totals and re.search(
        r"\b(combien|co[uû]t|total|combien\s+me\s+co[uû]tent)\b",
        request,
        re.IGNORECASE,
    ) and not expected_totals.intersection(mentioned_amounts):
        issues.append("La réponse ne présente pas le total du devis vérifié.")

    normalized_answer = normalize_text(answer).casefold()
    supported_zones: list[str] = []
    unsupported_delivery = False
    for entry in tool_results:
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        if entry.get("tool") == "calculer_livraison" and not result.get("success"):
            supported_zones.extend(result.get("available_zones", []))
            unsupported_delivery = result.get("supported") is False
        if entry.get("tool") == "convertir_devise" and result.get("success"):
            converted = _decimal_amount(result.get("converted_amount"))
            target = result.get("target_currency")
            if (
                converted is not None
                and isinstance(target, str)
                and (converted, _currency_code(target)) not in mentioned_currency_amounts
            ):
                issues.append("La conversion vérifiée doit apparaître dans la réponse.")
            rate_date = result.get("rate_date")
            if isinstance(rate_date, str) and rate_date not in answer:
                issues.append("La date du taux de change doit être indiquée.")
            rate = _decimal_amount(result.get("rate"))
            if (
                "taux" not in normalized_answer
                or rate is None
                or not any(
                    representation in answer
                    for representation in (
                        str(rate),
                        str(rate).replace(".", ","),
                    )
                )
            ):
                issues.append("Le taux de change réel doit être indiqué.")
    if supported_zones:
        normalized_zones = [normalize_text(zone).casefold() for zone in supported_zones]
        if any(zone not in normalized_answer for zone in normalized_zones):
            issues.append("La réponse doit lister les zones réellement desservies.")
    if unsupported_delivery and not any(
        phrase in normalized_answer
        for phrase in ("pas disponible", "non desserv", "ne livrons pas")
    ):
        issues.append("La zone non desservie doit être refusée clairement.")

    unavailable = [
        product
        for product in product_evidence
        if product.get("stock") == 0
    ]
    answer_folded = answer.casefold()
    if unavailable and not any(word in answer_folded for word in _OUT_OF_STOCK_WORDS):
        issues.append("La rupture de stock doit être annoncée clairement.")

    available_names = [
        product["product_name"]
        if "product_name" in product
        else product.get("name")
        for product in product_evidence
        if product.get("stock", 0) > 0
    ]
    available_names = [name for name in available_names if isinstance(name, str)]
    if unavailable:
        if not available_names:
            issues.append("Aucune alternative disponible n'a été vérifiée.")
        elif not any(name.casefold() in answer_folded for name in available_names):
            issues.append("Proposez une alternative disponible issue du catalogue.")

    return {"valid": not issues, "issues": issues, "request": request}


async def evaluer_reponse_llm(
    request: str,
    answer: str,
    tool_results: list[dict[str, Any]],
    *,
    client: Any,
    model: str,
) -> dict[str, Any]:
    """Ask RodiumAI to assess style and business rules after code checks pass."""
    code_check = verifier_reponse_code(request, answer, tool_results)
    if not code_check["valid"]:
        return {
            "valid": False,
            "issues": code_check["issues"],
            "llm_calls": 0,
            "cost_rodi": None,
        }

    evidence = json.dumps(tool_results, ensure_ascii=False)
    response = await client.chat(
        [
            {
                "role": "system",
                "content": (
                    "Tu évalues une réponse commerciale. Les résultats d'outils "
                    "sont la seule source de vérité. Retourne exclusivement un "
                    "objet JSON: {\"valid\": boolean, \"issues\": [string]}. "
                    "Rejette tout chiffre non justifié, les ruptures non signalées, "
                    "l'absence d'alternative vérifiée et toute violation métier. "
                    "Pour le taux de change, valide la date uniquement en la "
                    "comparant au champ rate_date renvoyé par l'outil. Ne la "
                    "rejette jamais sur la base de tes connaissances internes, "
                    "de ta date d'entraînement ou d'une date supposée."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "demande": request,
                        "reponse": answer,
                        "resultats_outils": evidence,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=model,
        max_tokens=200,
        temperature=0,
    )
    if not response.choices:
        return {"valid": False, "issues": ["Évaluation LLM sans résultat."]}
    content = response.choices[0].message.content or ""
    try:
        evaluation = json.loads(content)
    except json.JSONDecodeError:
        return {
            "valid": False,
            "issues": ["L'évaluation LLM n'a pas renvoyé un JSON valide."],
        }
    if not isinstance(evaluation, dict) or not isinstance(
        evaluation.get("valid"), bool
    ):
        return {
            "valid": False,
            "issues": ["Le résultat de l'évaluation LLM est invalide."],
        }
    issues = evaluation.get("issues", [])
    if not isinstance(issues, list) or not all(
        isinstance(issue, str) for issue in issues
    ):
        return {
            "valid": False,
            "issues": ["Le format des critiques LLM est invalide."],
        }
    has_verified_conversion = any(
        entry.get("tool") == "convertir_devise"
        and isinstance(entry.get("result"), dict)
        and entry["result"].get("success")
        for entry in tool_results
    )
    ignored_exchange_issues = []
    if has_verified_conversion:
        retained_issues = []
        for issue in issues:
            normalized_issue = normalize_text(issue).casefold()
            if any(
                term in normalized_issue
                for term in ("taux", "rate", "date", "futur", "future")
            ):
                ignored_exchange_issues.append(issue)
            else:
                retained_issues.append(issue)
        if not retained_issues and ignored_exchange_issues:
            evaluation["valid"] = True
        issues = retained_issues
    return {
        "valid": evaluation["valid"],
        "issues": issues,
        "ignored_exchange_issues": ignored_exchange_issues,
        "llm_calls": 1,
        "cost_rodi": response.cost_rodi,
    }