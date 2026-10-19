import base64
import json
import threading
from functools import partial
import keyring
import httplib2
from google_auth_httplib2 import AuthorizedHttp
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from app.core.config import OAUTH_FILE

SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'openid', 'https://www.googleapis.com/auth/userinfo.email']
SERVICE, ACCOUNT = 'PFE Mail Agent', 'google-oauth'

class Gmail:
    def __init__(self):
        self.lock = threading.RLock()
        self.connecting = False
        self.error = ''

    def _load(self):
        value = keyring.get_password(SERVICE, ACCOUNT)
        return json.loads(value) if value else None

    def status(self):
        try:
            with self.lock:
                data = self._load()
            return {'connected': bool(data), 'email': data['email'] if data else '', 'connecting': self.connecting,
                    'configured': OAUTH_FILE.is_file(), 'error': self.error}
        except Exception:
            return {'connected': False, 'email': '', 'connecting': False, 'configured': OAUTH_FILE.is_file(),
                    'error': 'Le coffre de mots de passe Windows est indisponible.'}

    def connect(self):
        if not OAUTH_FILE.is_file():
            raise ValueError('Ajoutez le fichier OAuth Desktop dans data/credentials.json. Consultez le guide Gmail.')
        with self.lock:
            if self.connecting:
                raise ValueError('Une connexion est déjà en cours dans votre navigateur.')
            keyring.get_password(SERVICE, ACCOUNT)  # fail before opening a browser if no secure vault
            self.connecting, self.error = True, ''
        threading.Thread(target=self._authorize, daemon=True).start()

    def _authorize(self):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_FILE), SCOPES, autogenerate_code_verifier=True)
            credentials = flow.run_local_server(host='127.0.0.1', port=0, open_browser=True, timeout_seconds=180,
                authorization_prompt_message='Autorisez PFE Mail Agent dans votre navigateur.',
                success_message='Compte connecté. Vous pouvez fermer cet onglet.', access_type='offline', prompt='consent')
            claims = id_token.verify_oauth2_token(credentials.id_token, partial(Request(), timeout=20), credentials.client_id)
            if not claims.get('email_verified'):
                raise ValueError('Adresse Google non vérifiée.')
            with self.lock:
                keyring.set_password(SERVICE, ACCOUNT, json.dumps({'email': claims['email'], 'credentials': json.loads(credentials.to_json())}))
        except Exception:
            self.error = 'Connexion Google interrompue ou refusée. Vérifiez le client Desktop et les utilisateurs de test.'
        finally:
            self.connecting = False

    def disconnect(self):
        with self.lock:
            if self.connecting:
                raise ValueError('Terminez la connexion en cours avant de déconnecter le compte.')
            if self._load():
                keyring.delete_password(SERVICE, ACCOUNT)
            self.error = ''

    def prepare(self):
        with self.lock:
            data = self._load()
            if not data:
                raise ValueError('Connectez votre compte Gmail.')
            credentials = Credentials.from_authorized_user_info(data['credentials'], SCOPES)
            if not credentials.valid:
                if not credentials.refresh_token:
                    raise ValueError('Reconnectez Gmail : autorisation expirée.')
                credentials.refresh(partial(Request(), timeout=20))
                keyring.set_password(SERVICE, ACCOUNT, json.dumps({'email': data['email'], 'credentials': json.loads(credentials.to_json())}))
            service = build('gmail', 'v1', http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=30)), cache_discovery=False)
            return data['email'], service

    def send(self, prepared, message):
        _, service = prepared
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')
        return service.users().messages().send(userId='me', body={'raw': raw}).execute(num_retries=0)['id']

gmail = Gmail()
