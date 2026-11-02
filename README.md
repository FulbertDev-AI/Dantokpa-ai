# Dantokpa AI

Assistant commercial en français pour consulter le catalogue, vérifier le
stock, calculer un devis, vérifier une livraison et convertir des montants
XOF en EUR ou NGN. Le projet utilise le function calling de RodiumAI et
propose une architecture à agent unique ainsi qu'une architecture multi-agents.

## Installation

Depuis la racine du projet, avec Python installé :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Renseignez ensuite les variables suivantes dans `.env` :

| Variable | Description |
| --- | --- |
| `RODIUMAI_API_KEY` | Clé API RodiumAI (requise). |
| `RODIUMAI_MODEL` | Modèle RodiumAI ; valeur par défaut : `openai/gpt-4o`. |
| `FRANKFURTER_API_URL` | Endpoint des taux Frankfurter ; une valeur par défaut est fournie. |
| `AFI_APPROVAL_CODE` | Code confidentiel utilisé par Afi pour approuver une commande. Laissez vide pour refuser toute commande. |

Ne publiez pas le fichier `.env` et ne partagez pas le code d'approbation.
`RODIUMAI_API_KEY` doit être configurée pour les appels au modèle.

## Lancement

```powershell
# Vérifier la connexion RodiumAI
python -m app.main --test-connection

# Traiter un message avec l'agent unique
python -m app.main --message "Avez-vous des pagnes ?"

# Traiter un message avec l'orchestration multi-agents
python -m app.main --multi-agent --message "Quel est le prix de trois pots de karité livrés à Porto-Novo ?"

# Démarrer la conversation interactive
python -m app.main
```

Le résultat affiche la réponse, les outils appelés, leurs arguments et résultats,
ainsi que la durée et les informations de coût disponibles.

## Outils et garde-fous

- **Vendeur** : recherche dans le catalogue, vérification du stock, devis et
  préparation de commande.
- **Logisticien** : zones et frais de livraison, conversion via les taux réels
  retournés par Frankfurter.
- **Rédacteur** : synthèse des résultats des spécialistes dans l'architecture
  multi-agents.
- Les prix, disponibilités et totaux proviennent du catalogue et des outils
  métier, et non d'estimations du modèle. Une commande ne contient pas les
  articles indisponibles.
- La création de commande exige d'abord la confirmation explicite du client,
  puis l'approbation interactive d'Afi. Le code d'Afi est saisi sans affichage ;
  il n'est pas fourni comme argument à l'agent. L'absence de code, une saisie
  incorrecte ou l'absence de confirmation bloque l'enregistrement.
- Les boucles d'agent sont bornées à huit étapes RodiumAI et huit appels
  d'outils. Les réponses sont évaluées à partir des résultats métier, puis
  contrôlées par l'évaluateur.
- La conversion prend en charge EUR et NGN à partir du XOF. Les zones de
  livraison actuellement prises en charge sont Cotonou, Akpakpa, Fidjrossè,
  Calavi, Porto-Novo et Ouidah.

Le catalogue et les commandes sont stockés dans `app/storage/products.json` et
`app/storage/orders.json`. Les tests de commandes utilisent des fichiers
temporaires.

## Tests

```powershell
python -m pytest -q
```

## Benchmark RodiumAI

`python -m app.benchmark` exécute les mêmes trois scénarios réels avec l'agent
unique et l'architecture multi-agents. La correction est vérifiée avec les
résultats des outils métier. Le coût est estimé à partir du nombre réel de
tokens et des tarifs RodiumAI par million de tokens lorsque ces données sont
disponibles. Les mesures ci-dessous correspondent à une exécution ; latence,
taux de change et coût peuvent varier selon le modèle, le service et le moment.

| Architecture | Réponses correctes | Appels LLM moyens | Durée moyenne | Coût total estimé |
| --- | ---: | ---: | ---: | ---: |
| Agent unique | 3/3 | 4,33 | 7,75 s | 21,9560548 RODI |
| Multi-agents | 3/3 | 5,00 | 8,36 s | 18,241538 RODI |

### Exemples de traces réelles

Exécution de l'agent unique pour « Vous avez des pagnes ? Combien ça fait en
euros pour ma sœur à Paris ? » :

```text
chercher_produits(query="pagne")
  -> Pagne wax 6 yards, 12 000 XOF, stock 14
convertir_devise(amount=12000, target_currency="EUR")
  -> 18,29 EUR ; taux 0,0015245 ; date du taux 2026-11-02
verifier_stock(product_id="P01")
  -> disponible, stock 14
```

Pour « Livrez-moi à Lomé ? », l'outil `calculer_livraison(zone="Lomé")` a
retourné `supported=false` et les six zones desservies ; l'agent a refusé la
livraison au lieu d'inventer une disponibilité.

Exécution pour « Je suis Koffi à Porto-Novo. Combien me coûtent 3 pots de
beurre de karité livrés, et ça fait combien en nairas ? » :

```text
chercher_produits(query="beurre de karité")
  -> Beurre de karité 500 g, 3 500 XOF l'unité
calculer_devis(items=[P06 x 3], delivery_zone="Porto-Novo")
  -> sous-total 10 500 XOF + livraison 3 000 XOF = 13 500 XOF
convertir_devise(amount=13500, target_currency="NGN")
  -> 30 973,05 NGN ; taux 2,2943 ; date du taux 2026-11-02
```
