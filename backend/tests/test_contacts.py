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
