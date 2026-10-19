# Vérifications du 19 octobre 2026

Environnement : Windows, Python 3.14, Node.js 24.18.0, npm 11.16.0.

- Suite pytest : 39 tests réussis — emails, imports CSV/XLSX, dédoublonnage, variables, HTML, MIME et PDF, OAuth simulé dans les tests, quotas, pause/reprise, persistance après arrêt, verrou de doublons, temporisation globale et documentation locale.
- Compilation TypeScript et Vite réussie ; Recharts séparé dans un bundle dédié.
- `pip check` : aucune dépendance incompatible.
- Vérification dans le navigateur avec une base SQLite temporaire séparée : création d’un contact, campagne en simulation, aperçu personnalisé, création du brouillon, démarrage et statut Simulé dans l’historique, consultation du contenu.
- Affichage contrôlé sur bureau et écran mobile de 390 pixels ; navigation et modales vérifiées.
- Lanceur Windows exécuté : démarrage des deux services, vérification des réponses HTTP, arrêt des processus et sous-processus, contrôle que les ports sont libérés, redémarrage réussi.
- La base principale reste vide ; aucune donnée de démonstration n’y est ajoutée.

**Non vérifié sur un compte réel :** consentement OAuth Google et transmission d’un email à Gmail. Le client OAuth de l’utilisateur est absent, aucun compte n’a été connecté et aucun email réel n’a été envoyé. Les tests utilisent exclusivement des transports et un coffre factices, sans accès à Google. Le code applicatif utilise le coffre Windows et le client Gmail officiel ; suivez GMAIL_SETUP.md puis effectuez un test explicite vers votre propre compte.

La suite peut signaler un avertissement de dépréciation dans la combinaison Starlette/httpx du client de test ; il ne concerne pas le fonctionnement du serveur ni les appels Google.
