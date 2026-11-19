# Aurora Model Catalog

**Une seule URL pour les applications :**

https://models-catalog.auroramind.fr/model-catalog.json

Ce fichier JSON public est mis à jour quotidiennement. Son [schéma JSON](https://models-catalog.auroramind.fr/model-catalog.schema.json) est disponible séparément pour les développeurs, mais n'est pas nécessaire pour le télécharger. Voir aussi le [guide complet d'installation et d'utilisation](INSTALLATION.md) et le [rapport public](RAPPORT-PUBLIC.md).

## Quel problème résout ce catalogue ?

Les fournisseurs publient leurs modèles, limites, capacités et tarifs à des endroits différents et les font évoluer régulièrement. Auroramind rassemble ces informations dans un fichier commun pour que toute application puissent choisir leurs modèles sans maintenir chacune leur propre liste.

Le catalogue décrit les offres. Il n'appelle pas les modèles, ne garantit pas qu'un compte y ait accès et ne remplace pas la documentation du fournisseur.

## Quels modèles sont disponibles ?

Le catalogue utilise les références publiques de Models.dev et LiteLLM. Il comprend notamment des modèles OpenAI, Anthropic, Google, Mistral, xAI, DeepSeek et Cohere. La liste évolue : le fichier publié fait foi pour les références recensées. Leur présence ne prouve pas qu'elles sont actives ou disponibles avec une clé donnée.

Les références explicitement rattachées au même modèle canonique sont regroupées dans une entrée `models`. Ses différentes offres restent dans `offers`, chacune avec son identifiant exact, ses capacités, tarifs et sources. Les références impossibles à rapprocher avec certitude restent des entrées distinctes marquées `grouping: "unresolved"`. Il peut donc rester des doublons : ils ne sont pas supprimés sur une simple ressemblance de nom. Les références `litellm.` ne correspondent pas nécessairement à un identifiant utilisable tel quel auprès d'une API.

## Quelles données sont disponibles ?

Pour chaque offre, lorsqu'elles sont connues : identité et alias, limites de contexte et de sortie, raisonnement et outils, modalités d'entrée, cache, tarifs standard ou conditionnels, cycle de vie et provenance. Les prix sont en USD par million de jetons. Seuls les tarifs attribuables aux fournisseurs directs explicitement reconnus sont renseignés ; les prix des plateformes intermédiaires sont exclus. La reconnaissance des fournisseurs directs et la couverture des données restent incomplètes.

`null` signifie **inconnu** : ce n'est ni un prix gratuit ni une fonctionnalité non prise en charge. Les valeurs et conditions peuvent évoluer ; vérifier leur provenance et la documentation officielle pour un usage sensible.

## Comment lire le fichier ?

```sh
curl --fail --compressed -o model-catalog.json https://models-catalog.auroramind.fr/model-catalog.json
```

Le fichier est autonome : pas de second fichier de données à télécharger. Exemple Python pour afficher les offres Google :

```python
import json

with open('model-catalog.json', encoding='utf-8') as f:
    catalog = json.load(f)

for model in catalog['models'].values():
    for offer in model['offers'].values():
        identity = offer['identity']
        if identity['provider'] == 'google':
            print(model['display_name'], identity['api_id'])
```

Le catalogue dispose d'un `checksum_sha256` stable pour détecter les changements réels. Avec le collecteur installé, la commande `aurora-model-catalog validate-clean --file model-catalog.json` vérifie sa structure, sa provenance et son checksum. En cas d'échec du téléchargement ou de la validation, conserver la dernière copie valide. `generated_at` et `sync_status` permettent d'évaluer la fraîcheur et l'état des sources ; le serveur peut conserver une réponse en cache pendant cinq minutes.

## Raisonnement et outils

Les informations sont propres à chaque offre, sous `offer["reasoning"]`. Préférer les champs de `reasoning.by_api` correspondant à l'API utilisée : `effort_levels`, `default_effort`, `compatible_with_tools`, `interleaved_tool_thinking` et les conditions connues dans `tool_use_conditions`. La liste générale `reasoning.effort_levels` peut provenir d'une source communautaire sans préciser l'API.

La compatibilité des outils avec le raisonnement ne doit pas être déduite de deux booléens séparés. Un champ absent ou `null` est inconnu. Les restrictions selon le mode, le niveau d'effort ou le choix forcé d'un outil ne sont pas toutes normalisées ; consulter la provenance et la documentation du fournisseur.

## Où mettre les clés ?

**Aucune clé n'est nécessaire pour télécharger ce catalogue.** Pour utiliser un modèle :

1. L'utilisateur crée son propre compte chez le fournisseur et y obtient une clé API.
2. Il configure cette clé **dans l'application qui appelle le modèle**, par exemple Nexus, selon la procédure de cette application.
3. L'application cliente utilise cette clé pour appeler le fournisseur. Aurora Model Catalog ne reçoit pas les clés des utilisateurs et ne teste pas leurs accès individuels.

Une application locale devrait utiliser le coffre de secrets du système. Une application hébergée doit conserver les clés côté serveur dans un gestionnaire de secrets isolé par utilisateur. Ne jamais placer une clé dans le catalogue, une URL, un journal ou du code partagé. Ce projet ne fournit pas d'écran de saisie ni de gestionnaire de clés pour Nexus : cette intégration reste à réaliser dans l'application cliente.

## Installer et exploiter le collecteur

Python 3.12+ est nécessaire :

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
pytest -m 'not integration'
```

Sur le serveur actuel, `scripts/daily-sync` actualise les sources, regroupe les références puis publie le fichier unique, sous verrou, chaque jour à **03:00 UTC**. La dernière version valide est conservée en cas d'échec. Le service cron et la machine doivent être actifs à l'heure prévue.

```sh
crontab -l
tail -n 100 logs/daily-sync.log
```

La collecte privée V1 OpenAI/Anthropic, les fichiers intermédiaires conservés pour compatibilité, le déploiement et les commandes de reconstruction sont détaillés dans le [guide complet](INSTALLATION.md). La collecte publique n'utilise pas les clés privées du propriétaire.
