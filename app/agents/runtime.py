import json
import logging
from time import perf_counter
from typing import Any, Callable

from app.services.rodium_client import MODEL, get_client

logger = logging.getLogger(__name__)


def _function_call_data(tool_call: Any) -> tuple[str, str, str]:
    function = tool_call.function
    return tool_call.id, function.name, function.arguments


async def executer_agent_outils(
    message: str,
    *,
    tools: list[dict[str, Any]],
    tool_functions: dict[str, Callable[..., dict]],
    system_prompt: str,
    client: Any = None,
    model: str = MODEL,
    max_steps: int = 8,
    max_tool_calls: int = 8,
) -> dict[str, Any]:
    """Run a bounded RodiumAI function-calling loop and retain its evidence."""
    if not 1 <= max_steps <= 8:
        raise ValueError("max_steps doit être compris entre 1 et 8.")
    if not 1 <= max_tool_calls <= 8:
        raise ValueError("max_tool_calls doit être compris entre 1 et 8.")

    active_client = client or get_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    trace: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    total_cost_rodi = 0.0
    has_cost = False
    llm_calls = 0

    for step in range(1, max_steps + 1):
        response = await active_client.chat(
            messages,
            model=model,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=700,
        )
        llm_calls += 1
        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise RuntimeError("RodiumAI a renvoyé une réponse sans choix.")

        message_data = choice.message
        messages.append(message_data.to_dict())
        cost = response.cost_rodi
        if isinstance(cost, (int, float)):
            total_cost_rodi += float(cost)
            has_cost = True

        tool_calls = message_data.tool_calls or []
        if not tool_calls:
            return {
                "answer": message_data.content or "",
                "trace": trace,
                "tool_results": tool_results,
                "llm_calls": llm_calls,
                "cost_rodi": total_cost_rodi if has_cost else None,
                "model": model,
            }

        reported_cost = False
        for tool_call in tool_calls:
            call_id, name, raw_arguments = _function_call_data(tool_call)
            started = perf_counter()
            arguments: dict[str, Any] | None = None
            if len(trace) >= max_tool_calls:
                result = {
                    "success": False,
                    "message": "La limite stricte d'appels d'outils est atteinte.",
                }
            else:
                try:
                    arguments = json.loads(raw_arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError(
                            "Les arguments de l'outil doivent être un objet JSON."
                        )
                    function = tool_functions.get(name)
                    if function is None:
                        result = {
                            "success": False,
                            "message": f"Outil inconnu : {name}.",
                        }
                    else:
                        result = function(**arguments)
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    logger.warning("Appel d'outil invalide (%s): %s", name, error)
                    result = {
                        "success": False,
                        "message": "Arguments d'outil invalides.",
                    }
                except (KeyError, OSError) as error:
                    logger.exception("Échec d'exécution de l'outil %s.", name)
                    result = {
                        "success": False,
                        "message": f"Échec de l'outil {name}.",
                        "error": type(error).__name__,
                    }

            elapsed = perf_counter() - started
            trace_entry = {
                "step": step,
                "tool": name,
                "arguments": arguments if arguments is not None else raw_arguments,
                "result": result,
                "duration_seconds": round(elapsed, 4),
                "cost_rodi": (
                    cost
                    if not reported_cost and isinstance(cost, (int, float))
                    else None
                ),
            }
            reported_cost = True
            trace.append(trace_entry)
            tool_results.append({"tool": name, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return {
        "answer": "",
        "trace": trace,
        "tool_results": tool_results,
        "llm_calls": llm_calls,
        "cost_rodi": total_cost_rodi if has_cost else None,
        "model": model,
        "error": "Limite stricte d'appels RodiumAI atteinte.",
    }
