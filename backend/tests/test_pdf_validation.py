import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject


def writer_with_page():
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    return writer


def pdf_bytes(writer):
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def upload(client, monkeypatch, tmp_path, content):
    from app.routers import api
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    return client.post('/api/documents', files={'file': ('CV.pdf', content, 'application/pdf')}, data={'kind': 'cv'})


@pytest.mark.parametrize('kind', ['view', 'named', 'goto', 'goto_indirect'])
def test_harmless_open_destination_accepted(client, monkeypatch, tmp_path, kind):
    writer = writer_with_page()
    destination = ArrayObject([writer.pages[0].indirect_reference, NameObject('/Fit')])
    action = {'view': destination, 'named': TextStringObject('FirstPage'),
              'goto': DictionaryObject({NameObject('/S'): NameObject('/GoTo'), NameObject('/D'): destination}),
              'goto_indirect': DictionaryObject({NameObject('/S'): NameObject('/GoTo'), NameObject('/D'): writer._add_object(destination)})}[kind]
    writer.root_object[NameObject('/OpenAction')] = writer._add_object(action)
    original = pdf_bytes(writer)
    result = upload(client, monkeypatch, tmp_path, original)
    assert result.status_code == 201, result.text
    # Preserve the user's original CV, including its content and metadata.
    assert client.get(f'/api/documents/{result.json()["id"]}/file').content == original


def test_recoverable_pdf_export_accepted(client, monkeypatch, tmp_path):
    original = pdf_bytes(writer_with_page())
    # Duplicate catalogue keys and shifted offsets occur in imperfect PDF exports.
    imperfect = original.replace(b'/Type /Catalog', b'/Type /Catalog /Type /Catalog')
    assert imperfect != original
    with pytest.raises(Exception):
        PdfReader(io.BytesIO(imperfect), strict=True)
    result = upload(client, monkeypatch, tmp_path, imperfect)
    assert result.status_code == 201, result.text


@pytest.mark.parametrize('kind', ['javascript', 'launch', 'chained'])
def test_unsafe_automatic_action_still_rejected(client, monkeypatch, tmp_path, kind):
    writer = writer_with_page()
    unsafe = DictionaryObject({NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('app.alert("test")')})
    if kind == 'javascript':
        writer.add_js('app.alert("test")')
    elif kind == 'launch':
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({NameObject('/S'): NameObject('/Launch'), NameObject('/F'): TextStringObject('test.exe')})
    else:
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({NameObject('/S'): NameObject('/GoTo'), NameObject('/D'): TextStringObject('FirstPage'), NameObject('/Next'): unsafe})
    result = upload(client, monkeypatch, tmp_path, pdf_bytes(writer))
    assert result.status_code == 400
    assert 'action automatique' in result.json()['detail']
    assert not (tmp_path / 'documents').exists()


def test_encrypted_pdf_specific_error(client, monkeypatch, tmp_path):
    writer = writer_with_page()
    writer.encrypt('password')
    result = upload(client, monkeypatch, tmp_path, pdf_bytes(writer))
    assert result.status_code == 400
    assert 'chiffré ou protégé' in result.json()['detail']


def test_broken_pdf_specific_error(client, monkeypatch, tmp_path):
    result = upload(client, monkeypatch, tmp_path, b'%PDF-1.7\nnot a PDF')
    assert result.status_code == 400
    assert 'Impossible de lire' in result.json()['detail']


def test_empty_pdf_specific_error(client, monkeypatch, tmp_path):
    result = upload(client, monkeypatch, tmp_path, pdf_bytes(PdfWriter()))
    assert result.status_code == 400
    assert 'aucune page' in result.json()['detail']
