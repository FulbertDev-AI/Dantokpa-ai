import json
import re
from time import perf_counter
from typing import Any

from app.agents.logisticien import INSTRUCTIONS_LOGISTICIEN, executer_logisticien
from app.agents.redacteur import INSTRUCTIONS_REDACTEUR, rediger_reponse
from app.agents.runtime import executer_agent_outils
from app.agents.tools import LOGISTICIEN_TOOLS, OUTILS, VENDEUR_TOOLS
from app.agents.vendeur import (
    INSTRUCTIONS_VENDEUR,
    appliquer_verifications_obligatoires,
    executer_vendeur,
)
from app.services.evaluator import (
    completer_conversion_verifiee,
    evaluer_reponse_llm,
    verifier_reponse_code,
)
from app.services.rodium_client import MODEL, get_client
from app.tools.products import normalize_text

MAX_LLM_CALLS = 8
_VENDOR_TERMS = (
    "pagne", "wax", "bazin", "sac", "raphia", "sandale", "robe",
    "beurre", "karite", "chemise", "stock", "produit", "prix",
    "combien", "commande", "catalogue", "fcfa", "article",
)
_LOGISTICS_TERMS = (
    "livr", "livraison", "euro", "eur", "naira", "ngn", "conversion",
)


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}", text) for term in terms)


def _intent(message: str) -> tuple[bool, bool]:
    normalized = normalize_text(message).casefold()
    return (
        _contains_term(normalized, _VENDOR_TERMS),
        _contains_term(normalized, _LOGISTICS_TERMS),
    )


def _append_agent_trace(
    trace: list[dict[str, Any]],
    agent_name: str,
    result: dict[str, Any],
) -> None:
    for entry in result.get("trace", []):
        trace.append({"agent": agent_name, **entry})


def _specialist_summary(
    agent_name: str,
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "specialiste": agent_name,
        "outils_utilises": [entry["tool"] for entry in tool_results],
        "resultats_verifies": tool_results,
    }


async def _correct_answer(
    request: str,
    summaries: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    critique: list[str],
    *,
    client: Any,
    model: str,
    system_prompt: str,
) -> dict[str, Any]:
    payload = {
        "demande_client": request,
        "resumes_specialistes": summaries,
        "resultats_verifies_des_outils": tool_results,
        "critiques": critique,
    }
    response = await client.chat(
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
        model=model,
        temperature=0,
        max_tokens=250,
    )
    if not response.choices:
        raise RuntimeError("RodiumAI n'a renvoyé aucune réponse de correction.")
    return {
        "answer": response.choices[0].message.content or "",
        "llm_calls": 1,
        "cost_rodi": response.cost_rodi,
    }


async def _evaluer_et_corriger(
    request: str,
    answer: str,
    summaries: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    *,
    client: Any,
    model: str,
    system_prompt: str,
    llm_calls: int,
    cost_rodi: float | None,
) -> dict[str, Any]:
    answer = completer_conversion_verifiee(answer, tool_results)
    code = verifier_reponse_code(request, answer, tool_results)
    if not code["valid"] and llm_calls < MAX_LLM_CALLS - 1:
        correction = await _correct_answer(
            request,
            summaries,
            tool_results,
            code["issues"],
            client=client,
            model=model,
            system_prompt=system_prompt,
        )
        answer = correction["answer"]
        answer = completer_conversion_verifiee(answer, tool_results)
        llm_calls += correction["llm_calls"]
        if isinstance(correction["cost_rodi"], (int, float)):
            cost_rodi = (cost_rodi or 0.0) + float(correction["cost_rodi"])
        code = verifier_reponse_code(request, answer, tool_results)

    evaluation = {"valid": False, "issues": code["issues"]}
    if code["valid"] and llm_calls < MAX_LLM_CALLS:
        evaluation = await evaluer_reponse_llm(
            request,
            answer,
            tool_results,
            client=client,
            model=model,
        )
        llm_calls += evaluation.get("llm_calls", 1)
        if isinstance(evaluation.get("cost_rodi"), (int, float)):
            cost_rodi = (cost_rodi or 0.0) + float(evaluation["cost_rodi"])

    if not evaluation["valid"] and llm_calls < MAX_LLM_CALLS:
        correction = await _correct_answer(
            request,
            summaries,
            tool_results,
            evaluation["issues"],
            client=client,
            model=model,
            system_prompt=system_prompt,
        )
        answer = correction["answer"]
        answer = completer_conversion_verifiee(answer, tool_results)
        llm_calls += correction["llm_calls"]
        if isinstance(correction["cost_rodi"], (int, float)):
            cost_rodi = (cost_rodi or 0.0) + float(correction["cost_rodi"])
        code = verifier_reponse_code(request, answer, tool_results)
        if code["valid"] and llm_calls < MAX_LLM_CALLS:
            evaluation = await evaluer_reponse_llm(
                request,
                answer,
                tool_results,
                client=client,
                model=model,
            )
            llm_calls += evaluation.get("llm_calls", 1)
            if isinstance(evaluation.get("cost_rodi"), (int, float)):
                cost_rodi = (cost_rodi or 0.0) + float(evaluation["cost_rodi"])

    valid = code["valid"] and evaluation["valid"]
    issues = [*code["issues"], *evaluation.get("issues", [])]
    if not valid:
        answer = (
            "Je ne peux pas confirmer ces informations avec les données "
            "vérifiées. Pouvez-vous préciser votre demande ?"
        )
    return {
        "answer": answer,
        "valid": valid,
        "evaluation": {"code": code, "llm": evaluation},
        "issues": issues,
        "llm_calls": llm_calls,
        "cost_rodi": cost_rodi,
    }


async def executer_agent_unique(
    message: str,
    *,
    client: Any = None,
    model: str = MODEL,
) -> dict[str, Any]:
    """Run the single-agent architecture with an eight-call hard ceiling."""
    started = perf_counter()
    active_client = client or get_client()
    explicit_delivery = _contains_term(
        normalize_text(message).casefold(),
        ("livr", "livraison", "livrer", "envoi"),
    )
    logistician_tools = (
        LOGISTICIEN_TOOLS
        if explicit_delivery
        else [
            tool
            for tool in LOGISTICIEN_TOOLS
            if tool["function"]["name"] != "calculer_livraison"
        ]
    )
    single_agent_functions = OUTILS.copy()
    if not explicit_delivery:
        single_agent_functions.pop("calculer_livraison")
    result = await executer_agent_outils(
        message,
        tools=[*VENDEUR_TOOLS, *logistician_tools],
        tool_functions=single_agent_functions,
        system_prompt=(
            INSTRUCTIONS_VENDEUR
            + "\n"
            + INSTRUCTIONS_LOGISTICIEN
            + "\n"
            + "Utilise uniquement les outils correspondant à la demande."
        ),
        client=active_client,
        model=model,
        max_steps=5,
    )
    result = appliquer_verifications_obligatoires(
        message,
        result,
        max_tool_calls=8,
    )
    checks = await _evaluer_et_corriger(
        message,
        result["answer"],
        [],
        result["tool_results"],
        client=active_client,
        model=model,
        system_prompt=INSTRUCTIONS_VENDEUR + "\n" + INSTRUCTIONS_LOGISTICIEN,
        llm_calls=result["llm_calls"],
        cost_rodi=result["cost_rodi"],
    )
    return {
        **checks,
        "architecture": "agent_unique",
        "tool_results": result["tool_results"],
        "trace": result["trace"],
        "duration_seconds": round(perf_counter() - started, 4),
        "model": model,
    }


async def orchestrer(
    message: str,
    *,
    client: Any = None,
    model: str = MODEL,
) -> dict[str, Any]:
    """Delegate relevant work to specialists, then evaluate the response."""
    started = perf_counter()
    active_client = client or get_client()
    needs_vendor, needs_logistics = _intent(message)
    trace: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    specialist_calls = 0
    cost_rodi: float | None = 0.0
    cost_known = False

    if needs_vendor and needs_logistics:
        vendor_budget, logistics_budget = 3, 1
    elif needs_vendor:
        vendor_budget, logistics_budget = 4, 0
    elif needs_logistics:
        vendor_budget, logistics_budget = 0, 4
    else:
        vendor_budget, logistics_budget = 0, 0

    if vendor_budget:
        vendor = await executer_vendeur(
            message,
            client=active_client,
            model=model,
            max_steps=vendor_budget,
            max_tool_calls=4 if needs_logistics else 8,
        )
        specialist_calls += vendor["llm_calls"]
        _append_agent_trace(trace, "vendeur", vendor)
        tool_results.extend(vendor["tool_results"])
        summaries.append(_specialist_summary("vendeur", vendor["tool_results"]))
        if isinstance(vendor["cost_rodi"], (int, float)):
            cost_rodi = (cost_rodi or 0.0) + float(vendor["cost_rodi"])
            cost_known = True

    if logistics_budget:
        logistics_request = message
        if tool_results:
            logistics_request += (
                "\n\nDonnées vérifiées utiles du Vendeur : "
                + json.dumps(tool_results, ensure_ascii=False)
            )
        logistician = await executer_logisticien(
            logistics_request,
            client=active_client,
            model=model,
            max_steps=logistics_budget,
            max_tool_calls=4,
            include_delivery=_contains_term(
                normalize_text(message).casefold(),
                ("livr", "livraison", "livrer", "envoi"),
            ),
        )
        specialist_calls += logistician["llm_calls"]
        _append_agent_trace(trace, "logisticien", logistician)
        tool_results.extend(logistician["tool_results"])
        summaries.append(_specialist_summary("logisticien", logistician["tool_results"]))
        if isinstance(logistician["cost_rodi"], (int, float)):
            cost_rodi = (cost_rodi or 0.0) + float(logistician["cost_rodi"])
            cost_known = True

    if specialist_calls >= MAX_LLM_CALLS:
        raise RuntimeError("Le budget d'appels LLM est épuisé avant la rédaction.")
    writer = await rediger_reponse(
        message,
        summaries,
        tool_results,
        client=active_client,
        model=model,
    )
    calls = specialist_calls + writer["llm_calls"]
    if isinstance(writer["cost_rodi"], (int, float)):
        cost_rodi = (cost_rodi or 0.0) + float(writer["cost_rodi"])
        cost_known = True

    checks = await _evaluer_et_corriger(
        message,
        writer["answer"],
        summaries,
        tool_results,
        client=active_client,
        model=model,
        system_prompt=INSTRUCTIONS_REDACTEUR,
        llm_calls=calls,
        cost_rodi=cost_rodi if cost_known else None,
    )
    return {
        **checks,
        "architecture": "multi_agents",
        "tool_results": tool_results,
        "trace": trace,
        "duration_seconds": round(perf_counter() - started, 4),
        "model": model,
    }