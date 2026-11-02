
from rodiumai import RodiumAI

from app.config import RODIUMAI_API_KEY, RODIUMAI_MODEL

MODEL = RODIUMAI_MODEL


def get_client() -> RodiumAI:
    """Crée le client officiel à la demande, après chargement du .env."""
    api_key = RODIUMAI_API_KEY
    if not api_key:
        raise RuntimeError(
            "RODIUMAI_API_KEY est absente ou vide dans le fichier .env."
        )

    return RodiumAI(
        api_key=api_key,
        default_model=MODEL,
        timeout=30.0,
        max_retries=2,
    )


async def test_connection(client: RodiumAI | None = None):
    """Vérifie la connexion réelle avec RodiumAI."""
    active_client = client or get_client()
    response = await active_client.chat(
        [
            {
                "role": "system",
                "content": "Tu es un assistant commercial."
            },
            {
                "role": "user",
                "content": "Réponds exactement : Dantokpa AI est connecté."
            }
        ],
        model=MODEL,
        max_tokens=100,
        temperature=0.2,
    )

    print("\nConnexion RodiumAI réussie !")
    print("Modèle :", MODEL)
    print("Réponse :", response.choices[0].message.content)
    print("Coût RODI :", response.cost_rodi)

    return response
