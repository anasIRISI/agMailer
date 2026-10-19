from app.models.entities import Campaign, Delivery
from app.services import queue

def make(client, **overrides):
    recipient = client.post('/api/recipients', json={'email': 'a@example.com'}).json()
    data = {'name': 'PFE', 'subject': 'PFE {{entreprise}}', 'body': 'Bonjour {{nom_recruteur}}', 'recipient_ids': [recipient['id']], **overrides}
    return client.post('/api/campaigns', json=data)

def test_pause_resume_stop(client, db):
    response = make(client)
    assert response.status_code == 201
    id_ = response.json()['id']
    assert client.post(f'/api/campaigns/{id_}/start', json={}).json()['status'] == 'running'
    assert client.post(f'/api/campaigns/{id_}/pause', json={}).json()['status'] == 'paused'
    assert client.post(f'/api/campaigns/{id_}/resume', json={}).json()['status'] == 'running'
    assert client.post(f'/api/campaigns/{id_}/stop', json={}).json()['status'] == 'cancelled'
    assert client.get('/api/history').json()[0]['status'] == 'cancelled'
    assert client.post(f'/api/campaigns/{id_}/start', json={}).status_code == 409

def test_real_send_requires_confirmation_and_gmail(client, monkeypatch):
    id_ = make(client, simulation=False).json()['id']
    assert client.post(f'/api/campaigns/{id_}/start', json={}).status_code == 400
    monkeypatch.setattr(queue.gmail, 'status', lambda: {'connected': False})
    assert client.post(f'/api/campaigns/{id_}/start', json={'confirm': True}).status_code == 400
    assert client.get('/api/history').json()[0]['status'] == 'draft'

def test_reservation_across_campaigns(client, monkeypatch):
    response = make(client, simulation=False)
    id_ = response.json()['id']
    monkeypatch.setattr(queue.gmail, 'status', lambda: {'connected': True, 'email': 'anas@example.com'})
    assert client.post(f'/api/campaigns/{id_}/start', json={'confirm': True}).status_code == 200
    recipient_id = client.get('/api/recipients').json()[0]['id']
    response = client.post('/api/campaigns', json={'name':'Duplicate','subject':'PFE','body':'Bonjour','recipient_ids':[recipient_id],'simulation':False})
    assert response.status_code == 409
    assert len(client.get('/api/campaigns').json()) == 1

def test_history_export_escaped(client):
    make(client, subject='=malicious')
    response = client.get('/api/history/export')
    assert response.status_code == 200
    assert "'=malicious" in response.text

def test_dashboard_empty(client):
    response = client.get('/api/dashboard')
    assert response.status_code == 200
    assert response.json()['recipients'] == 0

def test_swagger_resources_are_local(client):
    html = client.get('/docs').text
    assert '/docs-assets/swagger-ui-bundle.js' in html
    assert 'cdn.jsdelivr.net' not in html
    schema = client.get('/openapi.json').json()
    assert schema['components']['securitySchemes']['APIKeyHeader']['name'] == 'X-PFE-Client'

def test_tests_only_target_connected_address(client, db, monkeypatch):
    id_ = make(client).json()['id']
    monkeypatch.setattr(queue.gmail, 'status', lambda: {'connected': True, 'email': 'anas@example.com'})
    url = f'/api/campaigns/{id_}/test-send/self'
    assert client.post(url, json={}).status_code == 400
    test = client.post(url, json={'confirm': True})
    assert test.status_code == 200 and test.json()['is_test']
    item = client.get('/api/history', params={'campaign_id': test.json()['id']}).json()[0]
    assert item['email'] == 'anas@example.com'
    assert client.post(url, json={'confirm': True}).status_code == 409
    delivery = db.get(Delivery, item['id'])
    delivery.status = 'sent'
    db.commit()
    assert client.post(url, json={'confirm': True}).status_code == 200

def test_recipient_letter_snapshot_and_document_retention(client, db):
    from app.models.entities import Document
    cv = Document(name='cv.pdf', kind='cv', size=100, storage_name='cv.pdf', sha256='a')
    common = Document(name='lettre.pdf', kind='letter', size=100, storage_name='common.pdf', sha256='b')
    personal = Document(name='personnelle.pdf', kind='letter', size=100, storage_name='personal.pdf', sha256='c')
    db.add_all([cv, common, personal])
    db.commit()
    recipient = client.post('/api/recipients', json={'email':'a@example.com','entreprise':'Entreprise A','letter_document_id': personal.id}).json()
    campaign = client.post('/api/campaigns', json={'name':'PFE','subject':'PFE {{entreprise}}','body':'Bonjour','recipient_ids':[recipient['id']], 'document_ids':[cv.id,common.id]}).json()
    delivery = client.get('/api/history', params={'campaign_id':campaign['id']}).json()[0]
    assert delivery['document_ids'] == [cv.id,personal.id]
    assert delivery['subject'] == 'PFE Entreprise A'
    assert client.delete(f'/api/documents/{personal.id}').status_code == 409
    assert client.put(f'/api/recipients/{recipient["id"]}', json={'email':'a@example.com','entreprise':'New'}).status_code == 200
    assert client.get('/api/history').json()[0]['subject'] == 'PFE Entreprise A'
