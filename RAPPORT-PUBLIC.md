# Rapport du catalogue public V2

Relevé du 19 novembre 2026 : 16 954 entrées indexées sous 480 identifiants de source/fournisseur, dont 108 alias LiteLLM explicites. Les identifiants `litellm.*` sont des références de catalogue et ne constituent pas nécessairement des fournisseurs ou modèles uniques. Les doublons et offres de plateformes restent possibles. Les sources publiques Models.dev et LiteLLM et les tableaux officiels configurés répondaient lors de la collecte.

339 entrées ont au moins un prix standard renseigné. Aucun prix n'a été trouvé sur les entrées dont le fournisseur n'appartient pas à la liste de fournisseurs directs reconnus. Cette liste est volontairement limitée et ne couvre pas encore tous les créateurs : l'absence de prix ne signifie pas que l'offre est gratuite. Les prix de plateforme sont exclus ; il faut encore compléter les correspondances directes pour améliorer la couverture. Certains champs et conditions restent inconnus. Les tarifs communautaires ne sont pas nécessairement une vérification officielle en temps réel.

Le JSON est servi publiquement via HTTPS, avec compression gzip et cache de cinq minutes. La récupération complète a réussi, et le checksum du fichier téléchargé correspond au contenu. Les clés OpenAI et Anthropic configurées sur le serveur ne figuraient pas dans ce fichier. Le service public ne reçoit pas les clés des applications clientes et ne contacte pas les API privées des fournisseurs.

La tâche cron existante a été adaptée et exécutée manuellement avec succès. Le prochain passage planifié à 03:00 UTC devra être vérifié dans `logs/daily-sync.log`. Les dates et taux ci-dessus sont un instantané ; le JSON lui-même contient le dernier état de synchronisation.

## Mise à jour : raisonnement et outils

Le catalogue publié comprend désormais des listes de niveaux d'effort pour 5 562 références à partir de Models.dev ; ces listes générales ne précisent pas toujours l'API et peuvent inclure des références multiples d'un même modèle. Pour 13 entrées, une liste est également documentée pour une API précise à partir des documentations officielles. Cinq entrées ont une compatibilité explicite du raisonnement avec les outils, et du raisonnement entre appels d'outils, pour une API et un mode précis : quatre modèles Anthropic avec l'API Messages en mode adaptatif, et `deepseek-flash` avec Chat Completions en mode thinking. Les restrictions figurent dans `tool_use_conditions` et ne constituent pas une description exhaustive de toutes les combinaisons possibles.

Ces nombres sont un instantané et peuvent varier avec les sources. Les autres valeurs restent inconnues. La synchronisation quotidienne extrait les options déclarées par Models.dev et les informations structurées reconnues dans les pages officielles configurées ; elle ne déduit pas la compatibilité avec les outils à partir du nom du modèle ou de deux capacités séparées.

## Vue regroupée par modèle canonique

La vue publique `model-catalog.groups.v1.json` est un index indépendant du catalogue V2. À son premier relevé, elle regroupait 8 652 références dans 601 groupes canoniques ; 8 302 références restaient non regroupées faute de relation canonique suffisamment explicite. Chaque entrée du catalogue apparaît exactement une fois dans l'index. Une entrée regroupée reste distincte : ses caractéristiques, ses tarifs et sa provenance ne sont ni fusionnés ni transférés vers les autres membres.

Les applications doivent vérifier que `catalog_checksum_sha256` dans l'index correspond à `checksum_sha256` du catalogue V2. La synchronisation quotidienne régénère les deux fichiers ; si la source canonique est indisponible, le dernier index valide est conservé et son checksum permet de détecter une éventuelle différence avec le catalogue actualisé.

## Catalogue unifié

L'adresse recommandée pour les applications est désormais `https://models-catalog.auroramind.fr/model-catalog.json`. Ce fichier autonome contient les groupes et le détail de toutes leurs offres : il ne nécessite pas le téléchargement du catalogue V2 ni de l'index intermédiaire. Au premier relevé, il contenait 8 903 entrées de premier niveau : 601 groupes canoniques et 8 302 références non résolues, représentant ensemble 16 954 offres. Les références non résolues restent séparées ; ces chiffres ne sont donc pas un nombre garanti de modèles uniques. Les tarifs, capacités et provenances restent propres à chaque offre.
