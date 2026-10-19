import hashlib
import io
from types import SimpleNamespace
import pytest
from pypdf import PdfWriter
from app.services import rendering
from app.services.rendering import render, build_message

def pdf_content():
    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(out)
    return out.getvalue()

def test_neutral_variables_and_no_invention():
    subject, body = render('PFE {{poste}}', 'Bonjour {{nom_recruteur}}, candidature chez {{entreprise}}.', '', SimpleNamespace())
    assert subject == 'PFE informatique'
    assert body == 'Bonjour Madame, Monsieur, candidature chez votre entreprise.'
    assert '{{' not in body

def test_unknown_variable():
    with pytest.raises(ValueError):
        render('PFE', '{{inconnue}}', '', SimpleNamespace())

def test_header_injection_and_html():
    with pytest.raises(ValueError):
        render('{{entreprise}}', 'body', '', SimpleNamespace(entreprise='A\nBcc: x@example.com'))
    _, body = render('PFE', '<p>{{entreprise}}</p><img src="https://tracker.example/a"><script>x()</script>', '', SimpleNamespace(entreprise='<b>A</b>'), True)
    assert '<img' not in body and '<script' not in body
    assert '&lt;b&gt;A&lt;/b&gt;' in body

def test_mime_pdf_and_plain_alternative(tmp_path, monkeypatch):
    monkeypatch.setattr(rendering, 'DATA_DIR', tmp_path)
    (tmp_path / 'documents').mkdir()
    content = pdf_content()
    (tmp_path / 'documents' / 'a.pdf').write_bytes(content)
    doc = SimpleNamespace(size=len(content), storage_name='a.pdf', name='CV.pdf', sha256=hashlib.sha256(content).hexdigest())
    delivery = SimpleNamespace(email='rh@example.com', subject='Stage PFE', body='<p>Bonjour</p><p>Merci</p>', is_html=True, message_id='<abc@example.com>')
    message = build_message(delivery, 'anas@example.com', [doc])
    assert message['To'] == 'rh@example.com'
    assert message['Cc'] is None and message['Bcc'] is None
    assert message.get_body(preferencelist=('plain',)).get_content().strip() == 'Bonjour\n\nMerci'
    attachment = list(message.iter_attachments())[0]
    assert attachment.get_content_type() == 'application/pdf'
    assert attachment.get_payload(decode=True) == content
    (tmp_path / 'documents' / 'a.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError):
        build_message(delivery, 'anas@example.com', [doc])

def test_pdf_upload(client, monkeypatch, tmp_path):
    from app.routers import api
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    assert client.post('/api/documents', files={'file': ('fake.pdf', b'%PDF- rubbish', 'application/pdf')}).status_code == 400
    response = client.post('/api/documents', files={'file': ('../CV.pdf', pdf_content(), 'application/pdf')}, data={'kind': 'cv'})
    assert response.status_code == 201
    doc = response.json()
    assert doc['name'] == 'CV.pdf'
    assert client.get(f'/api/documents/{doc["id"]}/file').content.startswith(b'%PDF-')
