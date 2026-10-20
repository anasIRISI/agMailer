# PFE Mail Agent

Application locale Windows pour préparer et envoyer des candidatures PFE individuelles par Gmail. Interface française React/Vite/TypeScript/Tailwind avec composants Shadcn/Radix, Lucide et Recharts ; backend Python/FastAPI/SQLAlchemy/SQLite/APScheduler. Aucun service payant, hébergement cloud, Docker ou mot de passe Gmail requis.

## Démarrage Windows 11

Prérequis : **Python 3.11+**, **Node.js 20.19+** et npm dans le PATH, un navigateur et un compte Gmail. Développement vérifié avec Python 3.14 et Node 24. L’installation télécharge les dépendances depuis PyPI et npm ; l’usage métier communique avec Google uniquement pour OAuth et les envois. L’interface ne charge ni polices ni ressources distantes.

1. Double-cliquez sur **setup.bat** : création de `.venv`, installation Python et npm, compilation de l’interface, préparation de `data` et `.env`.
2. Double-cliquez sur **start.bat** : backend et frontend démarrés en arrière-plan, puis ouverture de [l’interface locale](http://127.0.0.1:5173).
3. Suivez [la configuration Gmail](docs/GMAIL_SETUP.md), puis connectez votre compte depuis **Paramètres Gmail**.
4. Pour arrêter, exécutez **stop.bat**. Les journaux sont dans `.runtime/`. Une campagne interrompue sera suspendue au redémarrage.

Les ports 8000 et 5173 doivent être libres. Les scripts ne ferment que les processus qu’ils ont créés, en vérifiant leur date de lancement. Ne démarrez pas plusieurs instances de l’application ni plusieurs workers Uvicorn sur la même base.

## Premier parcours

- **Destinataires** : ajoutez un contact ou importez un CSV UTF-8/XLSX. Colonne obligatoire : `email`. Colonnes facultatives : `entreprise`, `nom_recruteur`, `poste`. Les virgules, points-virgules et tabulations sont reconnus dans les CSV. Import maximum 5 Mo / 10 000 lignes, doublons normalisés et ignorés, rapport des lignes invalides.
- Pour réactiver toutes les adresses exclues : choisissez **Exclusions permanentes**, effacez toute recherche, cochez la case d’en-tête du tableau puis cliquez sur **Retirer l’exclusion**. La même action fonctionne sur une sélection partielle. Elle conserve les informations des contacts et les protections contre les doubles envois.
- Pour vider le carnet, cliquez sur **Tout supprimer** puis confirmez le nombre de destinataires. Le bouton **Supprimer (N)** agit uniquement sur la sélection. L’historique et les PDF restent conservés, les candidatures encore en brouillon ou en attente de ces contacts sont annulées. Les exclusions permanentes doivent être retirées explicitement avant la suppression ; si la sélection en contient, aucune suppression partielle n’est effectuée.
- **Documents** : importez un CV et une lettre PDF (8 Mo par document, 15 Mo cumulés). Visualisez-les avant utilisation. Une nouvelle version s’importe comme un nouveau document pour préserver les anciennes candidatures.
- Pour une lettre différente, modifiez un destinataire et choisissez son document personnalisé. Attribuez la même lettre aux contacts de l’entreprise concernée si nécessaire ; elle remplace les lettres communes de la campagne.
- **Modèles d’emails** : enregistrez votre objet, message texte ou HTML léger et signature. Variables : `{{entreprise}}`, `{{nom_recruteur}}`, `{{poste}}`. Les valeurs absentes deviennent « votre entreprise », « Madame, Monsieur » et « informatique ». Les variables inconnues sont rejetées.
- **Nouvelle campagne** : nommez la campagne, choisissez simulation ou réel, sélectionnez les contacts et PDF, rédigez le message puis examinez l’aperçu de chaque destinataire. Les données ne sont pas inventées. Enregistrez le brouillon.
- **Campagnes** : utilisez le test sur votre Gmail, puis Démarrer. Un envoi réel exige une confirmation. Pause suspend le traitement après la requête en cours ; Reprendre exige à nouveau une confirmation ; Arrêter annule les messages encore en attente.
- **Historique** : filtrez, consultez contenu et pièces jointes, exportez le CSV et marquez manuellement les réponses reçues. Un identifiant Gmail est conservé pour chaque message accepté.

L’application commence sans contacts, campagnes ou statistiques fictives. Le texte proposé dans l’éditeur est un point de départ modifiable. Aucun message n’est envoyé à l’ouverture ou au simple enregistrement d’une campagne.

## Fiabilité des envois

Chaque email est un message MIME individuel avec une seule adresse To, sans CC/BCC. Les messages HTML possèdent une alternative texte. L’application ne fait ni suivi d’ouverture ni lecture des messages Gmail.

La file est persistante dans SQLite. Les adresses exclues sont vérifiées au dernier moment. Les adresses réservées, acceptées par Gmail ou à vérifier bloquent les autres campagnes réelles. Les campagnes en simulation ne bloquent pas les candidatures réelles. Cette première version adopte une règle conservatrice : une seule candidature réelle par adresse. Les tests explicites sur votre propre Gmail sont identifiés séparément : un nouveau test est possible après le succès du précédent, mais un test encore en attente ou incertain bloque le suivant.

Les limites quotidiennes globales et de campagne se cumulent avec les restrictions Google ; la plus basse s’applique. Un délai global persistant évite de multiplier le débit en ouvrant plusieurs campagnes. Le fuseau journalier est Africa/Casablanca par défaut, modifiable dans `.env`.

Les problèmes avant la requête d’envoi peuvent être retentés de manière limitée avec backoff exponentiel. Après une requête au résultat incertain (timeout, panne, erreur Google 5xx), le message passe **À vérifier** et la campagne se suspend. Il ne sera pas renvoyé automatiquement. Vérifiez le dossier Messages envoyés de Gmail avec l’adresse, l’objet et le Message-ID. Les messages incertains comptent dans le plafond quotidien. Il n’y a pas de bouton de réenvoi d’un message incertain.

Un message déjà accepté par Google ne peut pas être rappelé. Le script stop force la fermeture des services ; pour terminer sans interrompre un appel Gmail, mettez d’abord les campagnes en pause dans l’interface. Au prochain lancement, les messages `in_progress` passent « À vérifier » et toutes les campagnes qui tournaient passent en pause. Aucune reprise automatique.

## Données et sécurité

- Base : `data/pfe.sqlite3`, créée au premier démarrage. PDF : `data/documents/`.
- Client OAuth : `data/credentials.json`. Tokens : coffre Windows, jamais dans le frontend, les logs ou SQLite. `.env.example` documente les chemins et le fuseau.
- Backend lié à 127.0.0.1 ; origines CORS locales ; en-tête requis pour les mutations ; hôtes contrôlés. N’exposez pas ces services sur le réseau.
- PDF vérifiés structurellement, noms de stockage générés, empreintes vérifiées avant envoi. Les documents utilisés ne peuvent pas être supprimés. HTML limité sans ressources externes ; aperçus sandbox ; SQL paramétré ; formules neutralisées dans les exports CSV.
- Aucune télémétrie. Les données SQLite et PDF restent lisibles par votre compte Windows : protégez votre session et vos sauvegardes.
- L’exclusion permanente conserve l’adresse ; vous devez retirer explicitement son exclusion avant de la supprimer ou changer l’adresse. L’historique garde les informations de candidature après suppression d’un contact.

Pour sauvegarder : arrêtez l’application, copiez `data/` et `.env` dans un emplacement protégé. Les tokens du coffre ne se copient pas avec le projet : reconnectez Gmail sur une autre machine. Pour révocation Google, consultez le guide. Pour une réinitialisation complète, sauvegardez puis retirez manuellement les données et déconnectez le coffre ; aucune suppression automatique n’est fournie.

## Développement et vérification

```powershell
# depuis la racine, après setup
.\.venv\Scripts\python.exe -m pytest
npm.cmd run build

# deux terminaux pour le développement
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
npm.cmd run dev
```

Tests sans réseau ni envois Google : emails invalides, CSV/XLSX, normalisation et doublons, rendu des variables, HTML, MIME et pièces jointes, uploads PDF, quotas, temporisation globale, autorisations, pause/reprise, reprise après interruption, refus et résultats incertains. Les mocks de transport sont exclusivement dans les tests. La version applicative appelle réellement Gmail.

La documentation interactive REST est disponible dans [Swagger local](http://127.0.0.1:8000/docs). Dans Swagger, cliquez sur **Authorize** et saisissez `local-app`. Pour un client REST, fournissez l’en-tête `X-PFE-Client: local-app` ; les commandes de campagne utilisent un corps `{"confirm":true}` pour les envois réels. Principaux groupes : `/api/recipients`, `/api/documents`, `/api/templates`, `/api/preview`, `/api/campaigns`, `/api/history`, `/api/dashboard`, `/api/gmail`, `/api/settings`.

Voir [l’architecture détaillée](docs/ARCHITECTURE.md). Le fichier `frontend/package-lock.json` fixe les dépendances frontend ; `requirements-lock.txt` indique les versions Python utilisées pour la validation. Les évolutions de schéma nécessiteront une migration : ne remplacez pas une base existante sans sauvegarde.

## Dépannage

- **Le navigateur n’ouvre pas l’application** : vérifiez `.runtime/backend-error.log` et `frontend-error.log`. Exécutez stop.bat puis start.bat. Vérifiez les ports 8000/5173.
- **npm ou Python introuvable** : installez les prérequis, activez l’option PATH et rouvrez le terminal.
- **Fichier OAuth manquant** : vérifiez le nom exact, sans suffixe `(1)` ni double extension, et le type Desktop.
- **Access denied Google / utilisateur non autorisé** : ajoutez le compte aux utilisateurs de test de votre projet ; vérifiez Gmail API et le consentement.
- **Token expiré / autorisation révoquée** : reconnectez Gmail puis reprenez manuellement la campagne après vérification.
- **Quota / blocage Google** : laissez la campagne suspendue jusqu’à résolution. Augmenter le plafond local ne contourne pas les restrictions Google.
- **À vérifier** : consultez Gmail manuellement. Ne recréez pas une candidature pour contourner le blocage.
- **Document impossible à supprimer** : il est utilisé dans une candidature ou comme lettre personnalisée. Importez une nouvelle version pour les prochaines campagnes.

Les tests et la compilation peuvent être exécutés sans compte Google. Le consentement OAuth et l’envoi réel nécessitent votre propre client Google et votre autorisation ; ils doivent être vérifiés sur votre compte avant une campagne réelle.
