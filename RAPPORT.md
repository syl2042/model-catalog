# Rapport de synchronisation V1

Relevé du 19 novembre 2026 avec les clés OpenAI et Anthropic configurées : toutes les sources ont répondu. Les découvertes officielles sont limitées aux modèles accessibles aux comptes concernés et ne constituent pas une liste universelle.

- **191 identifiants** : 167 OpenAI et 24 Anthropic.
- **Sources** : API officielles des deux fournisseurs, tableaux Markdown officiels de prix et modèles, Models.dev et LiteLLM.
- **43 divergences** dans `sync_status.conflicts`, à examiner au besoin ; un conflit ne signifie pas nécessairement qu'une source officielle est fausse.
- **14 modèles** comportent au moins une donnée issue d'une documentation officielle ; **32** ont au moins une variante tarifaire.
- Deux synchronisations consécutives n'ont produit aucun changement sémantique ; SHA-256 : `178bf4c8e26294ff47e14a33994d32bc068bbd852439ea7e5ebd922fc55c85a8`.

| Propriété | Modèles renseignés | Couverture |
|---|---:|---:|
| Nom affiché / famille | 71 | 37,2 % |
| Statut explicite | 28 | 14,7 % |
| Identifiant canonique | 26 | 13,6 % |
| Alias explicites | 2 | 1,0 % |
| Contexte d'entrée | 163 | 85,3 % |
| Limite de sortie | 162 | 84,8 % |
| Raisonnement | 129 | 67,5 % |
| Function calling | 153 | 80,1 % |
| Outils parallèles | 116 | 60,7 % |
| Sortie JSON par schéma | 129 | 67,5 % |
| Prix standard entrée | 178 | 93,2 % |
| Prix standard sortie | 168 | 88,0 % |
| Prix standard lecture cache | 131 | 68,6 % |
| Prix standard écriture cache | 43 | 22,5 % |
| Cache pris en charge | 135 | 70,7 % |
| Images | 145 | 75,9 % |
| PDF | 129 | 67,5 % |

Dénominateur : 191 identifiants de tous types, y compris modèles non textuels. Un `false` explicite compte comme renseigné. Les taux ne mesurent ni la fraîcheur ni l'applicabilité à un endpoint particulier.

L'extraction officielle est volontairement limitée aux tableaux et correspondances explicites reconnus. Les notes de prix ambiguës ne sont pas interprétées automatiquement ; les informations absentes des tableaux peuvent rester inconnues ou provenir d'une source communautaire. Les modes de service, cache, seuils et capacités par endpoint ne sont pas exhaustifs. Le schéma prévoit des informations plus détaillées que celles actuellement disponibles ; ne pas interpréter une absence comme `false`. Les modèles conservés lors d'un échec peuvent porter une provenance ancienne.

Les jeux Models.dev et LiteLLM utilisés sont sous licence MIT. `models.dev/api.json` est indexé par fournisseur ; `models.json` par modèle ; `catalog.json` contient `providers` et `models`. Le collecteur utilise `api.json`. Les sources et conditions de publication sont décrites dans le README.

Validation : 20 tests hors réseau et un test réseau réussis ; schéma et provenance vérifiés avant publication. Le script quotidien a été exécuté manuellement avec succès, puis enregistré dans cron pour 03:00 UTC. Le déclenchement à l'heure planifiée ne peut être confirmé qu'après son premier passage ; le service cron était actif lors de l'installation.
