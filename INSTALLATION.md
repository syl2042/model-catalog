# Installation et utilisation — Aurora Model Catalog

## Pour les applications clientes : une seule URL

Télécharger le catalogue unifié :

```sh
curl --fail --compressed -o model-catalog.json https://models-catalog.auroramind.fr/model-catalog.json
```

Ce fichier contient les modèles regroupés **et** le détail des offres : aucun second fichier de données n'est nécessaire. Le [schéma](https://models-catalog.auroramind.fr/model-catalog.schema.json) est disponible pour l'intégration et ne change pas cette procédure.

`models` est un dictionnaire. Une clé `canonical:<fournisseur>/<modèle>` représente un modèle dont les liens sont explicites ; `unresolved:<fournisseur>:<identifiant>` représente une référence qui n'a pas pu être rapprochée avec certitude. Chaque valeur contient :

- `grouping` : `canonical` ou `unresolved` ;
- `canonical_ref` et `display_name` lorsqu'ils sont connus ;
- `canonical_entry` lorsque l'entrée d'origine du modèle canonique est présente ;
- `offers` : dictionnaire des offres d'origine, chacune avec `identity`, `limits`, `reasoning`, `tools`, `pricing`, `cache`, `input_modalities` et `provenance`.

Une entrée `unresolved` contient une seule offre. Plusieurs références peuvent encore désigner le même modèle : elles restent distinctes lorsque la relation n'est pas suffisamment certaine. Le regroupement ne transfère jamais les prix ou capacités entre les offres. Les tarifs des plateformes intermédiaires restent inconnus ; seuls les tarifs de fournisseurs directs explicitement reconnus sont renseignés. `null` signifie inconnu, pas gratuit ni incompatible.

Exemple :

```python
import json

with open('model-catalog.json', encoding='utf-8') as f:
    catalogue = json.load(f)

modele = catalogue['models'].get('canonical:openai/gpt-5.4')
if modele:
    for cle_offre, offre in modele['offers'].items():
        identite = offre['identity']
        print(cle_offre, identite['provider'], identite['api_id'])
```

Le catalogue change chaque jour. La présence d'une offre ne garantit pas l'accès pour un utilisateur ni sa disponibilité actuelle. Les noms et identifiants des offres sont ceux des sources ; les références `litellm.` ne sont pas toutes des identifiants utilisables directement.

La validation complète avec le collecteur installé utilise une seule commande :

```sh
aurora-model-catalog validate-clean --file model-catalog.json
```

Elle vérifie le schéma, la provenance, l'unicité des offres et le checksum. JSON Schema seul ne vérifie pas le checksum. Pour le recalculer, partir de l'objet `models`, enlever `provenance` de chaque offre dans chaque dictionnaire `offers`, sérialiser en JSON UTF-8 avec les clés triées, les séparateurs compacts `,` et `:`, et Unicode non échappé, puis calculer SHA-256. `catalog_version` correspond aux 16 premiers caractères du checksum. Les dates et métadonnées de synchronisation sont exclues du checksum. Pour éviter les écarts de représentation numérique entre langages, préférer la commande de validation fournie.

Vérifier `schema_version`, `generated_at` et `sync_status`. Une application doit conserver sa dernière copie valide si un téléchargement ou une validation échoue. Le cache HTTP peut conserver une réponse cinq minutes.

## Raisonnement et outils

Les informations sont propres à chaque offre : `models[clé].offers[clé_offre].reasoning`. Préférer les champs de `by_api.<api>` : `effort_levels`, `default_effort`, `compatible_with_tools`, `interleaved_tool_thinking` et `tool_use_conditions`. Par exemple `messages` correspond à l'API Messages d'Anthropic et `responses` à l'API Responses d'OpenAI. La provenance figure dans l'offre, par chemin, comme `reasoning.by_api.messages.effort_levels`.

Une liste générale `reasoning.effort_levels` issue d'un catalogue communautaire peut ne pas préciser l'API. La compatibilité conjointe du raisonnement avec les outils ne doit pas être déduite de `reasoning.supported` et `tools.function_calling`. Les restrictions de mode ou de choix forcé d'outil ne sont pas toutes normalisées ; `tool_use_conditions` est un texte indicatif et ne garantit pas toutes les combinaisons.

## Clés des utilisateurs

Aucune clé API n'est demandée pour lire le catalogue. L'utilisateur obtient sa propre clé chez chaque fournisseur qu'il souhaite utiliser et la configure dans **l'application cliente qui appelle les modèles**, par exemple Nexus. Cette application est responsable de sa conservation sécurisée et de l'appel au fournisseur. Le catalogue ne reçoit pas ces clés et ne teste pas l'accès individuel.

Pour une application locale, utiliser un coffre de secrets du système. Pour une application hébergée, utiliser un gestionnaire de secrets côté serveur isolé par utilisateur. Ne jamais placer une clé dans ce JSON, une URL, un journal ou du code partagé. Ce projet ne fournit pas encore d'écran de saisie ni de gestionnaire de clés pour Nexus ; la procédure de saisie dépend de l'application cliente.

## Installation du collecteur

Pré-requis : Python 3.12+, accès HTTPS aux sources et répertoires inscriptibles. Depuis le projet :

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
pytest -m 'not integration'
```

Reconstruction locale de la chaîne publique :

```sh
aurora-model-catalog sync-public
aurora-model-catalog sync-groups
aurora-model-catalog sync-clean
aurora-model-catalog validate-clean --file public/model-catalog.json
```

Les trois commandes utilisent seulement des données publiques et ne nécessitent aucune clé. `sync-clean` vérifie que le catalogue source et l'index correspondent avant de produire le fichier unifié. Les étapes publient chacune atomiquement ; en cas d'échec, la dernière version valide de chaque fichier est conservée. Les anciens fichiers V2 et l'index regroupé restent accessibles pour compatibilité et dépannage, mais les clients ordinaires n'ont besoin que de l'URL unique ci-dessus.

Le propriétaire peut aussi effectuer une collecte **privée V1** OpenAI/Anthropic, distincte :

```sh
mkdir -p ~/.config/aurora-model-catalog
cp -n config.example.env ~/.config/aurora-model-catalog/credentials.env
chmod 600 ~/.config/aurora-model-catalog/credentials.env
# Modifier credentials.env avec les clés du propriétaire.
aurora-model-catalog sync
aurora-model-catalog validate
```

Ne pas publier `output/model-catalog.v1.json` : il peut révéler les identifiants accessibles au compte propriétaire. Les variables d'environnement explicites ont priorité sur le fichier ; `AURORA_CONFIG_FILE` permet de choisir un autre fichier de clés.

## Hébergement et synchronisation sur ce serveur

Caddy sert `https://models-catalog.auroramind.fr/model-catalog.json` et son schéma, ainsi que les anciens chemins maintenus pour compatibilité. Le conteneur statique `aurora-catalog-static` lit `public/` en lecture seule. La tâche cron lance `scripts/daily-sync` à 03:00 UTC : collecte publique, regroupement, publication du fichier unique puis collecte privée, sous verrou.

```sh
crontab -l
tail -n 100 logs/daily-sync.log
docker compose -f deploy/compose.yaml ps
curl -I https://models-catalog.auroramind.fr/model-catalog.json
```

Le service cron et la machine doivent être actifs. La publication unifiée a lieu seulement si ses sources et leur validation réussissent. Une source partielle est signalée dans `sync_status`. Les fichiers `deploy/compose.yaml` et `deploy/Caddyfile.fragment` décrivent le service statique et son routage. En cas de modification du schéma, actualiser également sa copie publique. Le collecteur et les correspondances de fournisseurs directs demandent une maintenance lorsque les sources changent.

## Docker et sources

Pour construire l'image :

```sh
docker build -t aurora-model-catalog .
```

Les commandes de la chaîne publique peuvent être exécutées dans le conteneur avec un volume partagé monté sur `/app/public`. Elles ne publient pas le résultat sur Internet. Sur le serveur, `docker compose -f deploy/compose.yaml up -d` gère le conteneur statique ; la configuration HTTPS est celle de Caddy.

Les données proviennent de [Models.dev](https://models.dev/) et du [fichier public LiteLLM](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json), complétés par certains tableaux officiels reconnus d'OpenAI, Anthropic et DeepSeek. La liste des sources et les dates sont dans le JSON. Les dépôts de données utilisés sont sous licence MIT ; les autres dépendances et les données de chaque fournisseur conservent leurs conditions propres.
