# Configuration Gmail et OAuth Desktop

1. Ouvrez [Google Cloud Console](https://console.cloud.google.com/). Créez un projet dédié « PFE Mail Agent ». Aucun abonnement ni facturation payante n’est nécessaire pour ce projet utilisant Gmail API.
2. Dans **API et services → Bibliothèque**, activez **Gmail API**.
3. Ouvrez **Google Auth Platform** (ou « Écran de consentement OAuth » selon l’interface). Renseignez le nom, votre adresse d’assistance et votre adresse de contact.
4. Configurez l’audience. Pour un compte Gmail personnel, choisissez l’audience externe. En état **Test**, ajoutez votre propre adresse Google dans les utilisateurs de test.
5. Dans **Accès aux données**, prévoyez les permissions `https://www.googleapis.com/auth/gmail.send`, `openid` et `https://www.googleapis.com/auth/userinfo.email`. L’application les demande automatiquement lors de la connexion. Ne demandez pas `gmail.readonly`, `gmail.modify` ou l’accès complet à la boîte.
6. Créez un **ID client OAuth**, type **Application de bureau**. Téléchargez son JSON. Le fichier doit contenir une clé `installed`, pas un client `web`. Aucun URI de redirection web à saisir : la bibliothèque ouvre un port loopback temporaire sur 127.0.0.1 avec PKCE et vérification de l’état OAuth.
7. Créez le dossier `data` à la racine et nommez le fichier téléchargé `credentials.json` à cet emplacement. Gardez ce fichier local et hors de Git. Si vous souhaitez un autre chemin, configurez `PFE_OAUTH_CLIENT_FILE` dans `.env` puis redémarrez le backend.
8. Lancez l’application, ouvrez **Paramètres Gmail → Connecter Gmail**. Un onglet de votre navigateur système s’ouvre. Choisissez le compte ajouté comme utilisateur de test et acceptez les permissions d’envoi et d’identification. Aucun mot de passe n’est saisi dans PFE Mail Agent.
9. L’adresse du compte apparaît après validation du jeton d’identité Google. Le token d’accès et le refresh token sont conservés dans le **Gestionnaire d’identification Windows**, entrée du service `PFE Mail Agent` / `google-oauth`. Aucun fichier token.json n’est créé. La connexion échoue si aucun coffre sécurisé n’est disponible.
10. Importez quelques contacts et vos documents. Créez d’abord une campagne en **simulation**, puis utilisez **Test sur mon Gmail** sur une campagne. Ce dernier bouton envoie réellement à votre propre compte et nécessite une confirmation explicite. Vérifiez le rendu et les PDF dans Gmail avant d’autoriser une campagne réelle.

En mode test externe, Google peut faire expirer les refresh tokens après sept jours pour ces permissions. Reconnectez le compte lorsque nécessaire. L’interface peut afficher un avertissement d’application non vérifiée pour votre projet personnel en test ; vérifiez que le projet et le client sont les vôtres. N’ouvrez pas l’application à d’autres utilisateurs sans étudier les exigences de vérification Google.

## Déconnexion et révocation

Le bouton Déconnecter supprime le token du coffre local et suspend les campagnes réelles. Pour révoquer aussi l’autorisation côté Google, utilisez [Connexions à des applications et services tiers](https://myaccount.google.com/connections). Une campagne déjà démarrée reste liée à son compte initial.

## Quotas et délivrabilité

Les unités de quota de l’API ne sont pas une autorisation d’envoyer autant de candidatures : les restrictions du compte Gmail et les contrôles Google s’appliquent également. Les plafonds locaux sont des limites supplémentaires et ne garantissent pas une capacité d’envoi. En cas de refus, quota ou blocage, l’application suspend la campagne ; ne reprenez qu’après avoir vérifié le compte. Aucun contournement, rotation de compte ou suivi invisible n’est utilisé.

Une réponse de succès signifie seulement que Gmail a accepté le message. Elle ne garantit pas une livraison en boîte principale, une réception ou une lecture. N’envoyez qu’à des contacts pertinents, personnalisez vos candidatures et enregistrez les refus dans les exclusions permanentes.

Références officielles : [OAuth pour applications natives](https://developers.google.com/identity/protocols/oauth2/native-app), [scopes Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes), [envoi de messages](https://developers.google.com/workspace/gmail/api/guides/sending), [quotas Gmail API](https://developers.google.com/workspace/gmail/api/reference/quota), [expiration et révocation OAuth](https://developers.google.com/identity/protocols/oauth2#expiration).
