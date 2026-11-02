import asyncio
from types import SimpleNamespace

import pytest

from app.agents.runtime import executer_agent_outils
from app.agents.tools import VENDEUR_FUNCTIONS
from app.agents.vendeur import appliquer_verifications_obligatoires
from app.agents.logisticien import executer_logisticien


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls or []

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ],
        }


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def chat(self, messages, **options):
        self.requests.append((list(messages), options.copy()))
        return self.responses.pop(0)


def fake_response(message, cost=0.01):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        cost_rodi=cost,
    )


def test_agent_executes_tool_and_observes_result():
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="lookup",
            arguments='{"item":"P01"}',
        ),
    )
    client = FakeClient(
        [
            fake_response(FakeMessage(tool_calls=[call])),
            fake_response(FakeMessage("P01 est disponible.")),
        ]
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "parameters": {
                    "type": "object",
                    "properties": {"item": {"type": "string"}},
                    "required": ["item"],
                },
            },
        }
    ]

    result = asyncio.run(
        executer_agent_outils(
            "Cherche P01",
            tools=tools,
            tool_functions={"lookup": lambda item: {"success": True, "item": item}},
            system_prompt="Use the provided tool.",
            client=client,
            model="test/model",
            max_steps=2,
        )
    )

    assert result["answer"] == "P01 est disponible."
    assert result["llm_calls"] == 2
    assert result["cost_rodi"] == 0.02
    assert result["trace"][0]["tool"] == "lookup"
    assert result["trace"][0]["result"]["item"] == "P01"
    assert client.requests[1][0][-1]["role"] == "tool"


def test_agent_has_a_strict_maximum_of_eight_calls():
    client = FakeClient([])
    with pytest.raises(ValueError, match="1 et 8"):
        asyncio.run(
            executer_agent_outils(
                "Bonjour",
                tools=[],
                tool_functions={},
                system_prompt="Test.",
                client=client,
                max_steps=9,
            )
        )


def test_agent_does_not_execute_tools_past_the_action_limit():
    calls = [
        SimpleNamespace(
            id=f"call-{index}",
            function=SimpleNamespace(
                name="lookup",
                arguments=f'{{"item":"P0{index}"}}',
            ),
        )
        for index in (1, 2)
    ]
    client = FakeClient(
        [
            fake_response(FakeMessage(tool_calls=calls)),
            fake_response(FakeMessage("Terminé.")),
        ]
    )
    executed = []

    result = asyncio.run(
        executer_agent_outils(
            "Recherche",
            tools=[],
            tool_functions={
                "lookup": lambda item: executed.append(item) or {"item": item}
            },
            system_prompt="Test.",
            client=client,
            max_steps=2,
            max_tool_calls=1,
        )
    )

    assert executed == ["P01"]
    assert result["trace"][1]["result"]["success"] is False
    assert result["llm_calls"] == 2


def test_required_stock_check_runs_for_availability_questions(monkeypatch):
    verified = []
    monkeypatch.setitem(
        VENDEUR_FUNCTIONS,
        "verifier_stock",
        lambda product_id: (
            verified.append(product_id)
            or {
                "success": True,
                "product_id": product_id,
                "product_name": "Pagne wax 6 yards",
                "stock": 14,
                "available": True,
            }
        ),
    )
    result = {
        "trace": [],
        "tool_results": [
            {
                "tool": "chercher_produits",
                "result": {
                    "success": True,
                    "products": [
                        {"id": "P01", "name": "Pagne wax 6 yards", "stock": 14}
                    ],
                },
            }
        ],
        "llm_calls": 1,
    }

    appliquer_verifications_obligatoires("Vous avez des pagnes ?", result)

    assert verified == ["P01"]
    assert result["tool_results"][-1]["tool"] == "verifier_stock"


def test_required_alternative_check_runs_for_out_of_stock_products(monkeypatch):
    searched = []
    verified = []
    monkeypatch.setitem(
        VENDEUR_FUNCTIONS,
        "chercher_produits",
        lambda query: (
            searched.append(query)
            or {
                "success": True,
                "products": [
                    {"id": "P01", "name": "Pagne wax 6 yards", "stock": 14}
                ],
            }
        ),
    )
    monkeypatch.setitem(
        VENDEUR_FUNCTIONS,
        "verifier_stock",
        lambda product_id: (
            verified.append(product_id)
            or {
                "success": True,
                "product_id": product_id,
                "product_name": "Pagne wax 6 yards",
                "stock": 14,
                "available": True,
            }
        ),
    )
    result = {
        "trace": [],
        "tool_results": [
            {
                "tool": "chercher_produits",
                "result": {
                    "success": True,
                    "products": [
                        {"id": "P03", "name": "Sac en raphia", "stock": 0}
                    ],
                },
            }
        ],
        "llm_calls": 1,
    }

    appliquer_verifications_obligatoires("C'est combien le sac ?", result)

    assert searched == ["*"]
    assert verified == ["P01"]


def test_logistician_cannot_calculate_delivery_without_a_delivery_request():
    client = FakeClient([fake_response(FakeMessage("Conversion seulement."))])

    asyncio.run(
        executer_logisticien(
            "Convertis le prix en euros pour ma sœur à Paris.",
            client=client,
            include_delivery=False,
            max_steps=1,
        )
    )

    tool_names = [
        tool["function"]["name"]
        for tool in client.requests[0][1]["tools"]
    ]
    assert tool_names == ["convertir_devise"]