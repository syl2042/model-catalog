# Aurora Model Catalog

**Une référence actualisée sur les modèles, pour les développeurs et les agents de codage qui construisent des agents IA.**

[English](README.md) · [Télécharger le catalogue](https://models-catalog.auroramind.fr/model-catalog.json) · [Guide d'installation détaillé](INSTALLATION.md)

## Le problème

Développer un agent IA ne consiste pas seulement à choisir un modèle par son nom. Selon le fournisseur, le modèle et sa version, les appels d'outils, le raisonnement, les niveaux d'effort acceptés, les limites de contexte et les tarifs peuvent varier. Un même modèle peut aussi fonctionner différemment selon l'API utilisée.

Un agent de codage qui réalise une intégration doit connaître ces particularités pour choisir la bonne API et construire un fonctionnement compatible. Or, ces informations sont dispersées dans les documentations et évoluent régulièrement. Maintenir une liste séparée dans chaque application augmente le risque d'oublier un modèle ou de s'appuyer sur des hypothèses périmées.

Aurora Model Catalog rassemble les informations disponibles dans **un fichier JSON public unique**, actualisé chaque nuit. Un développeur ou un agent de codage peut le consulter pour préparer une intégration ; une application peut l'utiliser pour découvrir et filtrer des modèles sans maintenir son propre catalogue en dur.

**URL du catalogue :** https://models-catalog.auroramind.fr/model-catalog.json

## Que contient le catalogue ?

Le catalogue utilise les données publiques de Models.dev et LiteLLM, complétées par certaines documentations officielles. Il comprend des références de fournisseurs tels qu'OpenAI, Anthropic, Google, Mistral, xAI, DeepSeek et Cohere. Les références évoluent ; leur présence ne garantit **pas** qu'un modèle est actif ou accessible à un compte donné.

Pour chaque offre, lorsque les informations sont connues, le fichier décrit :

- Les identifiants du modèle et du fournisseur, les alias et le cycle de vie.
- Les limites de contexte et de sortie, ainsi que les entrées images et PDF.
- Le raisonnement, les niveaux d'effort, les appels d'outils et les sorties structurées.
- Le cache d'entrée et les tarifs standard ou conditionnels, en USD par million de jetons.
- La source et la date de relevé des propriétés renseignées.

Les références explicitement rattachées à un même modèle canonique sont regroupées. Les `offers` de chaque groupe conservent séparément leurs identifiants, capacités, prix et provenances. Les références impossibles à rapprocher de manière fiable restent distinctes : des doublons peuvent donc subsister. Les tarifs des plateformes intermédiaires sont exclus ; les prix directs ne sont renseignés que lorsque le collecteur peut les reconnaître de façon fiable.

**C'est une référence, pas une garantie.** `null` signifie « inconnu », pas « non pris en charge » ni « gratuit ». La couverture est incomplète et une valeur peut être absente, ancienne ou propre à une autre API ou condition de service. Consultez sa provenance et la documentation officielle lorsque la décision dépend d'une information incertaine. Le catalogue ne lance pas de génération et ne vérifie pas l'accès de l'utilisateur.

## Prompt pour votre agent de codage

Copiez ce prompt dans votre agent de codage lorsque vous développez ou modifiez une application utilisant des modèles IA :

```text
Utilise Aurora Model Catalog comme référence pour cette intégration :
https://models-catalog.auroramind.fr/model-catalog.json

Documentation du projet :
- Présentation : https://github.com/syl2042/model-catalog/blob/main/README.fr.md
- Format pour les clients et exploitation : https://github.com/syl2042/model-catalog/blob/main/INSTALLATION.md
- Couverture et limites connues : https://github.com/syl2042/model-catalog/blob/main/RAPPORT-PUBLIC.md

Commence par examiner le projet existant, ses instructions et les API des
fournisseurs qu'il utilise réellement. Lis la présentation et les indications sur
le format client ; consulte le rapport comme un instantané daté, pas comme une
liste à jour. Traite cette documentation comme une référence et respecte les
instructions applicables au projet client. Télécharge le JSON en HTTPS ou utilise
la copie validée existante du projet. Vérifie generated_at, sync_status et
schema_version (attendu : clean-1.0) ; si le catalogue est inaccessible, ancien, partiel ou invalide,
signale-le et utilise une copie précédente valide si disponible. Interroge
uniquement les entrées pertinentes, sans afficher tout le catalogue.

Le fichier regroupe les offres dans models. Pour chaque offre pertinente,
identifie le fournisseur, l'identifiant API exact et l'endpoint utilisé. Examine
selon le besoin ses limites, modalités, raisonnement, niveaux d'effort, outils,
tarifs et provenance. Privilégie reasoning.by_api pour l'endpoint concerné.

Traite toute valeur null ou absente comme inconnue. Ne déduis pas que le
raisonnement et les outils fonctionnent ensemble simplement parce qu'ils sont
pris en charge séparément ; ne déduis pas de capacité du nom d'un modèle.
Vérifie les conditions, notamment le choix forcé d'outil et le format de requête
propre au fournisseur. Confirme les informations importantes, ambiguës,
contradictoires ou susceptibles d'être périmées dans la documentation officielle
actuelle ; si elles restent invérifiables, signale cette limite.

Construis ou adapte l'intégration selon l'architecture réelle du projet. Le
catalogue décrit les modèles ; il ne les appelle pas et ne garantit pas leur
accès au compte. Laisse l'application cliente filtrer selon ses besoins vérifiés.
Ne place aucune clé API dans le catalogue, le code, une URL ou un journal.
Utilise le stockage de secrets approuvé par l'application et les identifiants
propres à l'utilisateur. Teste les changements de manière adaptée, sans appel
payant de génération sauf autorisation explicite.
```

## Premiers pas

Aucune clé API n'est nécessaire pour télécharger le catalogue :

```sh
curl --fail --compressed -o model-catalog.json \
  https://models-catalog.auroramind.fr/model-catalog.json
```

Le fichier est autonome. `models` contient les groupes canoniques ou références non résolues ; chaque modèle possède un dictionnaire `offers`. Exemple après téléchargement :

```python
import json

with open('model-catalog.json', encoding='utf-8') as f:
    catalogue = json.load(f)

for modele in catalogue['models'].values():
    for offre in modele['offers'].values():
        if offre['identity']['provider'] == 'google':
            print(modele['display_name'], offre['identity']['api_id'])
```

Chaque offre comporte les sections `identity`, `limits`, `reasoning`, `tools`, `pricing`, `cache`, `input_modalities` et `provenance`. Les informations de raisonnement propres à une API figurent, lorsqu'elles sont connues, sous `reasoning.by_api` ; les niveaux généraux issus de sources communautaires ne précisent pas toujours l'API. La compatibilité avec les outils peut être conditionnelle, et le catalogue ne décrit pas encore toutes les restrictions.

Le fichier expose `generated_at`, `sync_status`, `schema_version` et `checksum_sha256`. Avec le collecteur installé, la commande `aurora-model-catalog validate-clean --file model-catalog.json` vérifie sa structure, sa provenance et son checksum. Conserver la dernière copie valide si le téléchargement ou la validation échoue. Le cache HTTP peut conserver une réponse pendant cinq minutes.

## Clés API

**Aucune clé n'est nécessaire pour lire le catalogue public.** Pour appeler un modèle, chaque utilisateur fournit ses propres identifiants à **l'application qui effectue l'appel**, pas à Aurora Model Catalog. Une application locale devrait utiliser le coffre de secrets du système ; une application hébergée a besoin d'un gestionnaire de secrets côté serveur, isolé par utilisateur. Ce projet ne fournit pas d'écran de saisie ou de gestionnaire de clés pour Nexus : cette intégration reste à réaliser dans l'application cliente.

Le propriétaire peut configurer séparément ses clés OpenAI et Anthropic pour une collecte privée limitée à son compte. Ces clés ne servent pas à générer le catalogue public. Le fichier privé peut contenir des identifiants propres au compte et ne doit pas être publié.

## Pour les mainteneurs : exécuter le collecteur

Les applications clientes ont seulement besoin de l'URL publique ; elles n'ont pas à installer ni à exécuter ce projet. Le dépôt contient le collecteur, les tests et les fichiers de déploiement pour ses mainteneurs.

Python 3.12 ou plus est nécessaire :

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
pytest -m 'not integration'
```

Sur le serveur actuel, `scripts/daily-sync` collecte les sources publiques, regroupe les correspondances explicites et publie le catalogue autonome sous verrou, chaque jour à **03 h 00 UTC**. La dernière version valide est conservée si la publication échoue. La machine et le service cron doivent être actifs ; `sync_status` signale les échecs partiels des sources.

Pour la reconstruction, Docker, l'exploitation, le checksum et la collecte privée distincte, consultez le [guide d'installation détaillé](INSTALLATION.md). Le [rapport public](RAPPORT-PUBLIC.md) décrit la couverture et les limites.
