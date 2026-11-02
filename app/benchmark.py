import asyncio
import json
from typing import Any

from app.agents.orchestrator import executer_agent_unique, orchestrer
from app.services.rodium_client import MODEL, get_client

SCENARIOS = [
    {
        "name": "pagne_en_euros",
        "message": (
            "Vous avez des pagnes ? Combien ça fait en euros pour ma sœur à Paris ?"
        ),
    },
    {
        "name": "livraison_lome",
        "message": "Livrez-moi à Lomé.",
    },
    {
        "name": "karite_naira",
        "message": (
            "Je suis Koffi à Porto-Novo. Combien me coûtent 3 pots de beurre "
            "de karité livrés, et ça fait combien en nairas ?"
        ),
    },
]


class TrackingClient:
    def __init__(self, client: Any):
        self._client = client
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages: list[dict], **options: Any) -> Any:
        response = await self._client.chat(messages, **options)
        usage = response.usage
        self.calls.append(
            {
                "cost_rodi": response.cost_rodi,
                "prompt_tokens": (
                    usage.prompt_tokens if usage is not None else None
                ),
                "completion_tokens": (
                    usage.completion_tokens if usage is not None else None
                ),
            }
        )
        return response


def _pricing_rates(pricing_response: dict[str, Any]) -> tuple[float, float] | None:
    for model_entry in pricing_response.get("data", []):
        if model_entry.get("model") != MODEL:
            continue
        pricing = model_entry.get("rodiumai_pricing", {})
        if pricing.get("pricing_unit") != "per_million_tokens":
            return None
        try:
            return (
                float(pricing["input_per_1m"]),
                float(pricing["output_per_1m"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _estimated_cost(
    calls: list[dict[str, Any]],
    rates: tuple[float, float] | None,
) -> float | None:
    if not calls:
        return None
    if all(isinstance(call["cost_rodi"], (int, float)) for call in calls):
        return sum(float(call["cost_rodi"]) for call in calls)
    if rates is None or any(
        not isinstance(call["prompt_tokens"], int)
        or not isinstance(call["completion_tokens"], int)
        for call in calls
    ):
        return None
    input_rate, output_rate = rates
    return sum(
        call["prompt_tokens"] * input_rate / 1_000_000
        + call["completion_tokens"] * output_rate / 1_000_000
        for call in calls
    )


def _successful_results(result: dict[str, Any], tool_name: str) -> list[dict]:
    return [
        entry["result"]
        for entry in result["tool_results"]
        if entry["tool"] == tool_name
        and isinstance(entry["result"], dict)
        and entry["result"].get("success")
    ]


def _correct_for_scenario(
    result: dict[str, Any],
    scenario_name: str,
) -> bool:
    if not result["valid"]:
        return False

    if scenario_name == "pagne_en_euros":
        conversions = _successful_results(result, "convertir_devise")
        searched = _successful_results(result, "chercher_produits")
        stock_checks = _successful_results(result, "verifier_stock")
        return (
            any(
                item["original_amount"] == 12000
                and item["target_currency"] == "EUR"
                for item in conversions
            )
            and any(
                any(product["id"] == "P01" for product in item["products"])
                for item in searched
            )
            and any(item.get("product_id") == "P01" for item in stock_checks)
        )

    if scenario_name == "livraison_lome":
        refusals = [
            entry["result"]
            for entry in result["tool_results"]
            if entry["tool"] == "calculer_livraison"
            and isinstance(entry["result"], dict)
        ]
        return any(
            item.get("success") is False
            and item.get("supported") is False
            and len(item.get("available_zones", [])) == 6
            for item in refusals
        )

    if scenario_name == "karite_naira":
        quotes = _successful_results(result, "calculer_devis")
        conversions = _successful_results(result, "convertir_devise")
        return (
            any(item.get("total") == 13500 for item in quotes)
            and any(
                item.get("original_amount") == 13500
                and item.get("target_currency") == "NGN"
                for item in conversions
            )
        )
    return False


async def run_benchmark() -> dict[str, Any]:
    """Run the same real RodiumAI scenarios against both architectures."""
    pricing_response = await get_client().pricing(MODEL)
    rates = _pricing_rates(pricing_response)
    report: dict[str, Any] = {
        "model": MODEL,
        "cost_basis": (
            "RodiumAI per-million-token prices × measured prompt/completion tokens"
            if rates
            else "RodiumAI did not provide token pricing or usage data."
        ),
        "architectures": {},
    }
    for architecture, runner in (
        ("agent_unique", executer_agent_unique),
        ("multi_agents", orchestrer),
    ):
        client = TrackingClient(get_client())
        measurements = []
        for scenario in SCENARIOS:
            call_start = len(client.calls)
            result = await runner(
                scenario["message"],
                client=client,
                model=MODEL,
            )
            cost = _estimated_cost(client.calls[call_start:], rates)
            measurements.append(
                {
                    "scenario": scenario["name"],
                    "correct": _correct_for_scenario(result, scenario["name"]),
                    "llm_calls": result["llm_calls"],
                    "duration_seconds": result["duration_seconds"],
                    "cost_rodi": cost,
                    "answer": result["answer"],
                    "trace": result["trace"],
                    "issues": result["issues"],
                }
            )

        known_costs = [
            item["cost_rodi"]
            for item in measurements
            if isinstance(item["cost_rodi"], (int, float))
        ]
        report["architectures"][architecture] = {
            "correct_answers": sum(item["correct"] for item in measurements),
            "scenarios": len(measurements),
            "average_llm_calls": sum(
                item["llm_calls"] for item in measurements
            )
            / len(measurements),
            "average_duration_seconds": sum(
                item["duration_seconds"] for item in measurements
            )
            / len(measurements),
            "total_cost_rodi": (
                sum(known_costs) if len(known_costs) == len(measurements) else None
            ),
            "measurements": measurements,
        }
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_benchmark()), ensure_ascii=False, indent=2))
