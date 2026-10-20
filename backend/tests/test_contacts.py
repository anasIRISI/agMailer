import io
import pytest
from openpyxl import Workbook
from sqlalchemy import select
from app.models.entities import Recipient
from app.schemas.api import clean_email
from app.services.importing import import_recipients

@pytest.mark.parametrize('email', ['bad', 'a\r\nb@example.com', 'a@', 'a b@example.com'])
def test_invalid_email(email):
    with pytest.raises(ValueError):
        clean_email(email)

def test_normalized_email():
    assert clean_email(' A@EXAMPLE.COM ') == 'a@example.com'

def test_csv_validation_and_duplicates(db):
    content = b'email,entreprise\na@example.com,A\nA@EXAMPLE.COM,B\nbad,C\n'
    report = import_recipients(db, content, 'a.csv')
    assert report['imported'] == 1
    assert report['duplicates'] == 1
    assert report['errors'][0]['line'] == 4
    assert import_recipients(db, content, 'a.csv')['imported'] == 0

def test_excel_import(db):
    wb = Workbook()
    wb.active.append(['email', 'entreprise', 'nom_recruteur', 'poste'])
    wb.active.append(['hr@example.com', 'Entreprise A', 'Mme Dupont', 'Stage IA'])
    output = io.BytesIO()
    wb.save(output)
    assert import_recipients(db, output.getvalue(), 'contacts.xlsx')['imported'] == 1
    assert db.scalar(select(Recipient)).poste == 'Stage IA'

def test_semicolon_utf8(db):
    report = import_recipients(db, '\ufeffemail;entreprise\na@example.com;Société\n'.encode('utf-8'), 'a.csv')
    assert report['imported'] == 1

def test_api_crud_and_exclusion(client):
    result = client.post('/api/recipients', json={'email': 'a@example.com'})
    assert result.status_code == 201
    id_ = result.json()['id']
    assert client.post('/api/recipients', json={'email': 'A@example.com'}).status_code == 409
    assert client.put(f'/api/recipients/{id_}', json={'email': 'a@example.com', 'excluded': True}).status_code == 200
    assert client.delete(f'/api/recipients/{id_}').status_code == 400
    assert client.get('/api/recipients').json()[0]['excluded'] is True

def test_origin_guard(client):
    assert client.post('/api/recipients', json={'email': 'a@example.com'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/recipients', headers={'Host': 'evil.example'}).status_code == 400

def test_bulk_exclusion_is_reversible_and_preserves_contact_details(client):
    first = client.post('/api/recipients', json={'email':'a@example.com','entreprise':'Entreprise A','nom_recruteur':'Service RH','poste':'Stage IA','excluded':True}).json()
    second = client.post('/api/recipients', json={'email':'b@example.com','excluded':True}).json()
    untouched = client.post('/api/recipients', json={'email':'c@example.com','excluded':True}).json()
    ids = [first['id'],second['id'],first['id']]
    response = client.patch('/api/recipients/exclusions', json={'recipient_ids':ids,'excluded':False})
    assert response.status_code == 200
    assert response.json()['updated'] == 2
    contacts = {r['id']:r for r in client.get('/api/recipients').json()}
    assert not contacts[first['id']]['excluded'] and not contacts[second['id']]['excluded']
    assert contacts[untouched['id']]['excluded']
    for field in ('email','entreprise','nom_recruteur','poste','letter_document_id'):
        assert contacts[first['id']][field] == first[field]
    assert client.patch('/api/recipients/exclusions', json={'recipient_ids':ids,'excluded':False}).json()['updated'] == 0
    assert client.patch('/api/recipients/exclusions', json={'recipient_ids':ids,'excluded':True}).json()['updated'] == 2

def test_bulk_exclusion_has_no_partial_update_for_missing_contact(client):
    item = client.post('/api/recipients', json={'email':'a@example.com','excluded':True}).json()
    result = client.patch('/api/recipients/exclusions', json={'recipient_ids':[item['id'],999999],'excluded':False})
    assert result.status_code == 404
    assert client.get('/api/recipients').json()[0]['excluded']

@pytest.mark.parametrize('ids', [[],[-1],[0]])
def test_bulk_exclusion_rejects_invalid_selection(client, ids):
    assert client.patch('/api/recipients/exclusions', json={'recipient_ids':ids,'excluded':False}).status_code == 422

def test_bulk_unexclude_preserves_duplicate_guard(client, db):
    from app.models.entities import Campaign, Delivery
    item = client.post('/api/recipients', json={'email':'a@example.com','excluded':True}).json()
    campaign = Campaign(name='PFE',subject='PFE',body='Bonjour',simulation=False,status='completed')
    db.add(campaign)
    db.flush()
    db.add(Delivery(campaign_id=campaign.id,recipient_id=item['id'],email=item['email'],subject='PFE',body='Bonjour',status='sent',gmail_id='already-sent'))
    db.commit()
    assert client.patch('/api/recipients/exclusions', json={'recipient_ids':[item['id']],'excluded':False}).status_code == 200
    contact = client.get('/api/recipients').json()[0]
    assert not contact['excluded'] and contact['contacted']
    result = client.post('/api/campaigns',json={'name':'Duplicate','subject':'PFE','body':'Bonjour','simulation':False,'recipient_ids':[item['id']]})
    assert result.status_code == 409

def test_bulk_delete_requires_confirmation_and_valid_selection(client):
    item = client.post('/api/recipients',json={'email':'a@example.com'}).json()
    url = '/api/recipients/bulk-delete'
    assert client.post(url,json={'recipient_ids':[item['id']]}).status_code == 400
    assert client.post(url,json={'recipient_ids':[],'confirm':True}).status_code == 422
    assert client.post(url,json={'recipient_ids':[item['id'],999999],'confirm':True}).status_code == 404
    assert len(client.get('/api/recipients').json()) == 1

def test_bulk_delete_does_not_silently_remove_permanent_exclusions(client):
    first = client.post('/api/recipients',json={'email':'a@example.com'}).json()
    excluded = client.post('/api/recipients',json={'email':'b@example.com','excluded':True}).json()
    result = client.post('/api/recipients/bulk-delete',json={'recipient_ids':[first['id'],excluded['id']],'confirm':True})
    assert result.status_code == 400
    assert len(client.get('/api/recipients').json()) == 2

def test_bulk_delete_preserves_history_cancels_pending_and_keeps_other_contacts(client, db):
    from app.models.entities import Campaign, Delivery
    first = client.post('/api/recipients',json={'email':'a@example.com'}).json()
    second = client.post('/api/recipients',json={'email':'b@example.com'}).json()
    untouched = client.post('/api/recipients',json={'email':'c@example.com'}).json()
    campaign = Campaign(name='PFE',subject='PFE',body='Bonjour',simulation=False,status='paused')
    db.add(campaign)
    db.flush()
    sent = Delivery(campaign_id=campaign.id,recipient_id=first['id'],email=first['email'],subject='PFE',body='Message envoyé',status='sent',gmail_id='gmail-kept',document_ids=[42])
    waiting = Delivery(campaign_id=campaign.id,recipient_id=second['id'],email=second['email'],subject='PFE',body='Message en attente',status='pending')
    draft = Delivery(campaign_id=campaign.id,recipient_id=first['id'],email='snapshot@example.com',subject='PFE',body='Brouillon',status='draft')
    db.add_all([sent,waiting,draft])
    db.commit()
    response = client.post('/api/recipients/bulk-delete',json={'recipient_ids':[first['id'],second['id'],first['id']],'confirm':True})
    assert response.status_code == 200 and response.json()['deleted'] == 2
    assert [r['id'] for r in client.get('/api/recipients').json()] == [untouched['id']]
    history = {d['id']:d for d in client.get('/api/history').json()}
    assert len(history) == 3
    assert history[sent.id]['gmail_id'] == 'gmail-kept' and history[sent.id]['status'] == 'sent'
    assert history[sent.id]['body'] == 'Message envoyé' and history[sent.id]['document_ids'] == [42]
    assert history[waiting.id]['status'] == history[draft.id]['status'] == 'cancelled'
    assert all(d['recipient_id'] is None for d in history.values())
    restored = client.post('/api/recipients',json={'email':'a@example.com'}).json()
    result = client.post('/api/campaigns',json={'name':'Duplicate','subject':'PFE','body':'Bonjour','simulation':False,'recipient_ids':[restored['id']]})
    assert result.status_code == 409

def test_single_contact_delete_cancels_its_unsent_delivery(client, db):
    from app.models.entities import Campaign, Delivery
    item = client.post('/api/recipients',json={'email':'a@example.com'}).json()
    campaign = Campaign(name='PFE',subject='PFE',body='Bonjour',simulation=True,status='draft')
    db.add(campaign)
    db.flush()
    db.add(Delivery(campaign_id=campaign.id,recipient_id=item['id'],email=item['email'],subject='PFE',body='Bonjour',status='draft'))
    db.commit()
    assert client.delete(f'/api/recipients/{item["id"]}').status_code == 200
    assert client.get('/api/history').json()[0]['status'] == 'cancelled'
