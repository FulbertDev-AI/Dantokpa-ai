
import argparse
import asyncio
import json

from app.agents.orchestrator import executer_agent_unique, orchestrer
from app.services.rodium_client import test_connection


def afficher_resultat(result: dict) -> None:
    print(f"\n{result['answer']}")
    print("\n--- Trace des outils ---")
    for entry in result["trace"]:
        print(
            f"[{entry.get('agent', 'agent')}] {entry['tool']} "
            f"args={json.dumps(entry['arguments'], ensure_ascii=False)}"
        )
        print(f"  résultat={json.dumps(entry['result'], ensure_ascii=False)}")
        print(
            f"  durée={entry['duration_seconds']} s | "
            f"coût RODI={entry['cost_rodi']}"
        )
    print(
        f"\nÉvaluation : {'valide' if result['valid'] else 'refusée'}"
        f" | appels LLM : {result['llm_calls']}"
        f" | coût RODI total : {result['cost_rodi']}"
        f" | durée : {result['duration_seconds']} s"
    )
    if result["issues"]:
        print("Critiques :", "; ".join(result["issues"]))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant commercial Dantokpa AI")
    parser.add_argument("--message", help="Traite un message puis quitte.")
    parser.add_argument(
        "--multi-agent",
        action="store_true",
        help="Utilise l'architecture multi-agents.",
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Effectue un vrai appel de vérification à RodiumAI.",
    )
    args = parser.parse_args()

    if args.test_connection:
        await test_connection()
        return

    async def traiter(message: str) -> None:
        result = (
            await orchestrer(message)
            if args.multi_agent
            else await executer_agent_unique(message)
        )
        afficher_resultat(result)

    if args.message:
        await traiter(args.message)
        return

    print("Dantokpa AI est prêt. Tapez 'quitter' pour arrêter.")
    while True:
        message = input("\nClient : ").strip()
        if message.casefold() in {"quitter", "quit", "exit"}:
            break
        if message:
            await traiter(message)


if __name__ == "__main__":
    asyncio.run(main())
