import asyncio
from types import SimpleNamespace

from app.services.evaluator import (
    completer_conversion_verifiee,
    evaluer_reponse_llm,
    verifier_reponse_code,
)


def quote_evidence():
    return [
        {
            "tool": "calculer_devis",
            "result": {
                "success": True,
                "available_items": [
                    {
                        "product_name": "Robe en wax",
                        "unit_price": 22000,
                        "quantity": 2,
                        "stock": 5,
                        "line_total": 44000,
                    }
                ],
                "unavailable_items": [
                    {
                        "product_name": "Sac en raphia",
                        "unit_price": 7500,
                        "quantity": 1,
                        "stock": 0,
                    }
                ],
                "subtotal": 44000,
                "delivery_fee": 2000,
                "total": 46000,
            },
        }
    ]


def test_code_evaluator_accepts_verified_quote_and_alternative():
    result = verifier_reponse_code(
        "Je veux 2 robes en wax et 1 sac en raphia livrés à Calavi",
        (
            "Le sac en raphia est en rupture. Je peux vous proposer la "
            "Robe en wax. Total : 46 000 FCFA."
        ),
        quote_evidence(),
    )

    assert result["valid"] is True
    assert result["issues"] == []


def test_code_evaluator_rejects_wrong_total():
    result = verifier_reponse_code(
        "Combien coûtent ces articles livrés ?",
        "Total : 44 000 FCFA.",
        quote_evidence(),
    )

    assert result["valid"] is False
    assert any("total" in issue.lower() for issue in result["issues"])


def test_code_evaluator_rejects_unverified_amount():
    result = verifier_reponse_code(
        "Combien coûte le produit ?",
        "Le prix est de 99 000 FCFA.",
        quote_evidence(),
    )

    assert result["valid"] is False
    assert any("pas étayé" in issue for issue in result["issues"])


def test_code_evaluator_requires_stock_notice_and_alternative():
    result = verifier_reponse_code(
        "Quel est le prix du sac ?",
        "Le sac en raphia coûte 7 500 FCFA.",
        quote_evidence(),
    )

    assert result["valid"] is False
    assert any("rupture" in issue.lower() for issue in result["issues"])
    assert any("alternative" in issue.lower() for issue in result["issues"])


def test_code_evaluator_reads_nested_order_tool_results():
    result = verifier_reponse_code(
        "Combien coûtent les robes livrées ?",
        (
            "Le sac en raphia est en rupture. Une alternative disponible est "
            "le Pagne wax 6 yards. Total : 46 000 FCFA."
        ),
        [
            {
                "tool": "creer_commande",
                "result": {
                    "success": True,
                    "order": {
                        "items": [
                            {
                                "product_name": "Robe en wax",
                                "unit_price": 22000,
                                "quantity": 2,
                                "line_total": 44000,
                            }
                        ],
                        "unavailable_items": [
                            {
                                "product_name": "Sac en raphia",
                                "unit_price": 7500,
                                "quantity": 1,
                                "stock": 0,
                            }
                        ],
                        "suggested_alternative": {
                            "product_name": "Pagne wax 6 yards",
                            "price": 12000,
                            "stock": 14,
                        },
                        "subtotal": 44000,
                        "delivery_fee": 2000,
                        "total": 46000,
                    },
                },
            }
        ],
    )

    assert result["valid"] is True


def test_code_evaluator_requires_conversion_rate_and_date():
    evidence = [
        {
            "tool": "convertir_devise",
            "result": {
                "success": True,
                "original_amount": 12000,
                "original_currency": "XOF",
                "converted_amount": 18.29,
                "target_currency": "EUR",
                "rate": 0.001524,
                "rate_date": "2026-11-02",
            },
        }
    ]

    result = verifier_reponse_code(
        "Quel est le prix en euros ?",
        "Cela fait 18,29 EUR au taux de 0,001524 EUR par XOF au 2026-11-02.",
        evidence,
    )

    assert result["valid"] is True
    assert result["issues"] == []


def test_conversion_completion_uses_only_api_values():
    evidence = [
        {
            "tool": "convertir_devise",
            "result": {
                "success": True,
                "original_amount": 12000,
                "original_currency": "XOF",
                "converted_amount": 18.29,
                "target_currency": "EUR",
                "rate": 0.0015245,
                "rate_date": "2026-11-02",
            },
        }
    ]

    answer = completer_conversion_verifiee("Le pagne coûte 12 000 FCFA.", evidence)

    assert "18,29 EUR" in answer
    assert "0.0015245" in answer
    assert "2026-11-02" in answer
    result = verifier_reponse_code(
        "Quel est le prix en euros ?",
        answer,
        evidence,
    )
    assert result["valid"] is True


def test_code_evaluator_requires_refusal_and_supported_delivery_zones():
    evidence = [
        {
            "tool": "calculer_livraison",
            "result": {
                "success": False,
                "supported": False,
                "available_zones": [
                    "cotonou",
                    "akpakpa",
                    "fidjrosse",
                    "calavi",
                    "porto-novo",
                    "ouidah",
                ],
            },
        }
    ]

    result = verifier_reponse_code(
        "Livrez-moi à Lomé.",
        (
            "La livraison n'est pas disponible à Lomé. Zones desservies : "
            "Cotonou, Akpakpa, Fidjrossè, Calavi, Porto-Novo et Ouidah."
        ),
        evidence,
    )

    assert result["valid"] is True


def test_llm_evaluator_cannot_override_code_rejection():
    class Client:
        async def chat(self, *args, **kwargs):
            raise AssertionError("LLM must not run after a code rejection.")

    result = asyncio.run(
        evaluer_reponse_llm(
            "Quel est le prix ?",
            "Le prix est 99 000 FCFA.",
            quote_evidence(),
            client=Client(),
            model="test/model",
        )
    )

    assert result["valid"] is False
    assert result["llm_calls"] == 0


def test_llm_evaluator_does_not_override_verified_exchange_date():
    class Client:
        async def chat(self, *args, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"valid":false,"issues":['
                                '"The rate date is in the future."'
                                ']}'
                            )
                        )
                    )
                ],
                cost_rodi=None,
            )

    evidence = [
        {
            "tool": "convertir_devise",
            "result": {
                "success": True,
                "original_amount": 12000,
                "converted_amount": 18.29,
                "target_currency": "EUR",
                "rate": 0.0015245,
                "rate_date": "2026-11-02",
            },
        }
    ]
    answer = (
        "18,29 EUR au taux 0,0015245, date du taux 2026-11-02."
    )

    result = asyncio.run(
        evaluer_reponse_llm(
            "Prix en euros ?",
            answer,
            evidence,
            client=Client(),
            model="test/model",
        )
    )

    assert result["valid"] is True
    assert len(result["ignored_exchange_issues"]) == 1
