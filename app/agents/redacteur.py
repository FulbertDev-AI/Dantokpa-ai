import json
from typing import Any

from app.services.rodium_client import MODEL, get_client

INSTRUCTIONS_REDACTEUR = """
Tu es le Rédacteur de Dantokpa AI. Tu n'as aucun outil commercial.
Réponds au client à partir des seuls résultats vérifiés transmis par le Gérant.
Ne complète jamais une donnée manquante, n'invente ni prix, ni stock, ni frais,
ni taux. Suis les critiques d'évaluation si elles sont fournies, sans jamais
contredire les résultats vérifiés. Ton professionnel, naturel, court, français
adapté à WhatsApp; moins de 80 mots.
Pour une conversion, indique le montant, le taux exact et sa date. Pour une
zone refusée, indique le refus et toutes les zones desservies.
"""


async def rediger_reponse(
    request: str,
    summaries: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    *,
    client: Any = None,
    model: str = MODEL,
    critique: list[str] | None = None,
) -> dict[str, Any]:
    """Writes a concise customer response without access to sales tools."""
    active_client = client or get_client()
    payload = {
        "demande_client": request,
        "resumes_specialistes": summaries,
        "resultats_verifies_des_outils": tool_results,
        "critiques": critique or [],
    }
    response = await active_client.chat(
        [
            {"role": "system", "content": INSTRUCTIONS_REDACTEUR},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
        model=model,
        temperature=0.2,
        max_tokens=250,
    )
    if not response.choices:
        raise RuntimeError("RodiumAI n'a renvoyé aucune réponse du Rédacteur.")
    return {
        "answer": response.choices[0].message.content or "",
        "llm_calls": 1,
        "cost_rodi": response.cost_rodi,
    }