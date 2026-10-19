import json
from types import SimpleNamespace
from app.services import gmail as module

def test_secure_storage_status_disconnect(monkeypatch):
    vault = {}
    monkeypatch.setattr(module.keyring, 'get_password', lambda service, account: vault.get(account))
    monkeypatch.setattr(module.keyring, 'delete_password', lambda service, account: vault.pop(account))
    gmail = module.Gmail()
    assert not gmail.status()['connected']
    vault[module.ACCOUNT] = json.dumps({'email': 'anas@example.com', 'credentials': {}})
    assert gmail.status()['email'] == 'anas@example.com'
    gmail.disconnect()
    assert not gmail.status()['connected']

def test_refresh_persists_new_tokens(monkeypatch):
    stored = []
    creds = SimpleNamespace(valid=False, refresh_token='secret', client_id='client', to_json=lambda: '{"refresh_token":"new-secret"}')
    creds.refresh = lambda request: stored.append('refreshed')
    monkeypatch.setattr(module.Credentials, 'from_authorized_user_info', lambda data, scopes: creds)
    monkeypatch.setattr(module.keyring, 'get_password', lambda *args: '{"email":"anas@example.com","credentials":{}}')
    monkeypatch.setattr(module.keyring, 'set_password', lambda service, account, value: stored.append(json.loads(value)))
    monkeypatch.setattr(module, 'AuthorizedHttp', lambda *args, **kwargs: object())
    monkeypatch.setattr(module, 'build', lambda *args, **kwargs: 'service')
    email, service = module.Gmail().prepare()
    assert email == 'anas@example.com' and service == 'service'
    assert stored[0] == 'refreshed'
    assert stored[1]['credentials']['refresh_token'] == 'new-secret'

def test_google_send_has_no_automatic_retries():
    calls = []
    class Service:
        def users(self): return self
        def messages(self): return self
        def send(self, **kwargs):
            calls.append(kwargs)
            return self
        def execute(self, **kwargs):
            calls.append(kwargs)
            return {'id': 'abc'}
    message = SimpleNamespace(as_bytes=lambda: b'MIME')
    assert module.Gmail().send(('anas@example.com', Service()), message) == 'abc'
    assert calls[0]['userId'] == 'me'
    assert calls[1]['num_retries'] == 0
