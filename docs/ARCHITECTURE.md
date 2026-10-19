# Architecture de PFE Mail Agent

Le navigateur React communique uniquement avec `/api` sur Vite. Le proxy local transmet les requêtes à FastAPI sur 127.0.0.1:8000. FastAPI utilise SQLAlchemy et SQLite en mode WAL. APScheduler examine la file toutes les deux secondes. Un verrou de processus empêche deux instances de piloter la même base ; un verrou d’envoi sérialise les décisions de campagne et les appels externes.

```
frontend/src/
  components/       composants partagés, éditeur, primitives Shadcn / Radix
  pages/            huit pages fonctionnelles en français
  hooks/            chargement et actualisation des données
  services/         client REST
  types/            contrats TypeScript
  layouts/          navigation et cadre de l’application
backend/app/
  core/             chemins, limites, origines
  database/         moteur SQLite, sessions, horodatage UTC
  models/           destinataires, documents, modèles, campagnes, livraisons, paramètres
  schemas/          validation Pydantic
  repositories/     requêtes de réservation et sérialisation
  services/         import, rendu, MIME, OAuth, moteur d’envoi
  routers/          API REST documentée dans Swagger
backend/tests/      tests métier et API sans connexion à Google
```

## États et prévention des doublons

Une campagne naît en `draft`. Chaque livraison contient une copie du destinataire, du message rendu et des identifiants de documents. Le démarrage confirmé réserve les adresses en passant les livraisons à `pending`. Le moteur contrôle à nouveau exclusions, documents, compte Gmail, quota quotidien et temporisation globale avant l’envoi.

Avant d’appeler Google, il valide et enregistre `in_progress`, la date, l’expéditeur et un Message-ID MIME. Il désactive les retries internes du client Google. Une réponse avec identifiant Gmail devient `sent`. Une simulation construit le MIME et devient `simulated`, sans utiliser Google.

Une exception réseau ou une erreur Google 5xx après le début de la requête devient `check`. Un arrêt du programme dans l’état `in_progress` produit aussi `check`. Ces adresses restent bloquées et ne sont jamais relancées automatiquement. Le Message-ID facilite la recherche manuelle dans Gmail ; il ne fournit pas une garantie d’idempotence côté Google.

Une réponse explicite de quota/limitation suspend la campagne et conserve le message en attente. Une erreur d’autorisation suspend aussi la campagne. Les erreurs de connexion/actualisation avant la requête d’envoi peuvent être retentées trois fois avec délais de 30, 60, 120 secondes. Les refus définitifs deviennent `failed`.

La validation et la réservation des adresses sont protégées par le verrou de l’unique processus. Une contrainte SQL empêche la répétition d’une adresse dans une même campagne. Une adresse en attente, en cours, acceptée ou incertaine dans une campagne réelle bloque toute autre candidature réelle. L’objectif conservateur est une seule candidature réelle par adresse ; aucune action de réenvoi en masse n’est exposée.

Les campagnes en cours sont systématiquement mises en pause au redémarrage. Le lancement de l’application ne reprend jamais une campagne. La limite quotidienne utilise Africa/Casablanca, les dates stockées sont en UTC. Les tests réels passent aussi par la file et comptent dans les limites.

## Stockage et confidentialité

SQLite et les PDF se trouvent dans `data/`. Les noms de stockage sont générés et les contenus PDF sont vérifiés avec pypdf. Leur empreinte SHA-256 est vérifiée avant construction MIME. Les documents référencés restent conservés pour l’historique. Leur remplacement crée une nouvelle version sélectionnable dans les futures campagnes.

OAuth Desktop utilise PKCE et le serveur loopback de la bibliothèque Google. Les tokens ne sont jamais envoyés au frontend ni écrits dans SQLite : keyring utilise le coffre Windows. Les seules permissions sont `gmail.send`, `openid` et l’adresse email ; aucun accès en lecture à Gmail.

Les mutations nécessitent un en-tête spécifique et une origine autorisée. Le backend limite les hôtes locaux et les origines CORS. Les données métier passent par SQLAlchemy. L’HTML est réduit à un sous-ensemble sans liens, images, scripts ou pixels. Les aperçus sont isolés dans des iframes sandbox. L’export CSV neutralise les formules de tableur.

## Limites explicites

L’application doit rester mono-processus et locale, sans `--reload` pour les campagnes réelles. Le verrou de fichier refuse une deuxième instance. Les tables sont créées automatiquement ; cette première version ne comporte pas de migration de schéma pour les versions futures.

Une pause attend la fin de l’appel Gmail en cours ; un message déjà accepté ne peut pas être rappelé. Le script d’arrêt Windows ferme les processus qu’il a démarrés, et toute requête interrompue est traitée comme incertaine au redémarrage. La portée Gmail ne permet pas de vérifier automatiquement l’état « À vérifier », les réponses, les lectures ou les rebonds.

Les PDF sont validés structurellement ; cela ne remplace pas un antivirus. Les fichiers et la base ne sont pas chiffrés par l’application : utilisez un compte Windows protégé et éventuellement BitLocker. Seuls les tokens sont protégés par le coffre système. Aucun secret n’est stocké dans le navigateur.
