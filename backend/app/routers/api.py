import csv
import io
import hashlib
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from fastapi.security import APIKeyHeader
from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import Session
from app.core.config import DATA_DIR, MAX_PDF, MAX_ATTACHMENTS
from app.database.session import get_db, now
from app.models.entities import Recipient, Document, Template, Campaign, Delivery, Setting
from app.schemas.api import RecipientInput, RecipientExclusionInput, RecipientBulkDeleteInput, TemplateInput, CampaignInput, PreviewInput, ActionInput, SettingsInput
from app.repositories.queries import as_dict, contacted
from app.services.importing import import_recipients
from app.services.rendering import render
from app.services.gmail import gmail
from app.services.queue import SEND_LOCK, used_today, settings, day_start
from app.services.pdf_validation import validate_pdf, PDFValidationError

router = APIRouter(prefix='/api', dependencies=[Depends(APIKeyHeader(name='X-PFE-Client', auto_error=False))])
DB = Depends(get_db)

def require(db, model, id_):
    value = db.get(model, id_)
    if value is None:
        raise HTTPException(404, 'Élément introuvable.')
    return value

def checked_documents(db, ids):
    docs = [require(db, Document, x) for x in dict.fromkeys(ids)]
    if sum(x.size for x in docs) > MAX_ATTACHMENTS:
        raise HTTPException(400, 'Les pièces jointes dépassent 15 Mo.')
    return docs

@router.get('/health')
def health():
    return {'status': 'ok'}

@router.get('/recipients')
def recipients(db: Session = DB):
    contacted_emails = set(db.scalars(select(Delivery.email).join(Campaign).where(Campaign.simulation.is_(False), Campaign.is_test.is_(False), Delivery.status.in_(['sent', 'check', 'pending', 'in_progress']))))
    return [{**as_dict(r), 'contacted': r.email in contacted_emails} for r in db.scalars(select(Recipient).order_by(Recipient.id.desc()))]

@router.post('/recipients', status_code=201)
def add_recipient(data: RecipientInput, db: Session = DB):
    if db.scalar(select(Recipient.id).where(Recipient.email == data.email)):
        raise HTTPException(409, 'Cette adresse existe déjà.')
    if data.letter_document_id:
        require(db, Document, data.letter_document_id)
    item = Recipient(**data.model_dump())
    db.add(item)
    db.commit()
    return as_dict(item)

@router.patch('/recipients/exclusions')
def update_exclusions(data: RecipientExclusionInput, db: Session = DB):
    with SEND_LOCK:
        ids = set(data.recipient_ids)
        items = list(db.scalars(select(Recipient).where(Recipient.id.in_(ids))))
        if len(items) != len(ids):
            raise HTTPException(404, 'Un destinataire sélectionné est introuvable. Actualisez la liste avant de réessayer.')
        updated = 0
        for item in items:
            if item.excluded != data.excluded:
                item.excluded = data.excluded
                updated += 1
        db.commit()
        return {'updated': updated, 'excluded': data.excluded}

@router.put('/recipients/{id_}')
def edit_recipient(id_: int, data: RecipientInput, db: Session = DB):
    item = require(db, Recipient, id_)
    if db.scalar(select(Recipient.id).where(Recipient.email == data.email, Recipient.id != id_)):
        raise HTTPException(409, 'Cette adresse existe déjà.')
    if item.excluded and data.email != item.email:
        raise HTTPException(400, 'Retirez explicitement l’exclusion avant de changer cette adresse.')
    if data.letter_document_id:
        require(db, Document, data.letter_document_id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return as_dict(item)

def remove_contacts(db, items):
    ids = [item.id for item in items]
    if any(item.excluded for item in items):
        raise HTTPException(400, 'Certains contacts sont dans la liste d’exclusion permanente. Retirez d’abord leur exclusion avant de les supprimer.')
    db.execute(update(Delivery).where(Delivery.recipient_id.in_(ids), Delivery.status.in_(['draft', 'pending'])).values(
        status='cancelled', error='Destinataire supprimé avant l’envoi.'))
    db.execute(update(Delivery).where(Delivery.recipient_id.in_(ids)).values(recipient_id=None))
    db.execute(delete(Recipient).where(Recipient.id.in_(ids)))
    db.commit()

@router.post('/recipients/bulk-delete')
def delete_contacts(data: RecipientBulkDeleteInput, db: Session = DB):
    if not data.confirm:
        raise HTTPException(400, 'Confirmez la suppression des destinataires sélectionnés.')
    with SEND_LOCK:
        ids = set(data.recipient_ids)
        items = list(db.scalars(select(Recipient).where(Recipient.id.in_(ids))))
        if len(items) != len(ids):
            raise HTTPException(404, 'Un destinataire sélectionné est introuvable. Actualisez la liste avant de réessayer.')
        remove_contacts(db, items)
        return {'deleted': len(items)}

@router.delete('/recipients/{id_}')
def delete_recipient(id_: int, db: Session = DB):
    with SEND_LOCK:
        remove_contacts(db, [require(db, Recipient, id_)])
    return {'ok': True}

@router.post('/recipients/import')
async def import_file(file: UploadFile = File(...), db: Session = DB):
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, 'Import limité à 5 Mo.')
    try:
        return import_recipients(db, content, file.filename or '')
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else 'Fichier illisible. Utilisez CSV UTF-8 ou XLSX.') from None

@router.get('/documents')
def documents(db: Session = DB):
    return [as_dict(x) for x in db.scalars(select(Document).order_by(Document.id.desc()))]

@router.post('/documents', status_code=201)
async def upload_document(file: UploadFile = File(...), kind: str = Form('cv'), db: Session = DB):
    if kind not in ('cv', 'letter', 'other'):
        raise HTTPException(400, 'Type de document invalide.')
    content = await file.read(MAX_PDF + 1)
    if len(content) > MAX_PDF or not content.startswith(b'%PDF-') or not (file.filename or '').lower().endswith('.pdf'):
        raise HTTPException(400, 'Utilisez un PDF valide de 8 Mo maximum.')
    try:
        validate_pdf(content)
    except PDFValidationError as exc:
        raise HTTPException(400, str(exc)) from None
    storage = f'{uuid4().hex}.pdf'
    folder = DATA_DIR / 'documents'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / storage).write_bytes(content)
    name = Path((file.filename or 'document.pdf').replace('\\', '/')).name
    name = ''.join(ch for ch in name if ord(ch) >= 32)[:200]
    item = Document(name=name, kind=kind, size=len(content), storage_name=storage, sha256=hashlib.sha256(content).hexdigest())
    db.add(item)
    db.commit()
    return as_dict(item)

@router.get('/documents/{id_}/file')
def document_file(id_: int, db: Session = DB):
    doc = require(db, Document, id_)
    path = DATA_DIR / 'documents' / doc.storage_name
    if not path.is_file():
        raise HTTPException(404, 'Fichier absent du disque.')
    return FileResponse(path, media_type='application/pdf', filename=doc.name, content_disposition_type='inline', headers={'Content-Security-Policy': "frame-ancestors 'self'"})

@router.delete('/documents/{id_}')
def delete_document(id_: int, db: Session = DB):
    doc = require(db, Document, id_)
    if any(id_ in d.document_ids for d in db.scalars(select(Delivery))) or db.scalar(select(Recipient.id).where(Recipient.letter_document_id == id_)):
        raise HTTPException(409, 'Document utilisé par une candidature ou une lettre personnalisée. Il est conservé pour l’historique.')
    (DATA_DIR / 'documents' / doc.storage_name).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {'ok': True}

@router.get('/templates')
def templates(db: Session = DB):
    return [as_dict(t) for t in db.scalars(select(Template))]

@router.post('/templates', status_code=201)
def create_template(data: TemplateInput, db: Session = DB):
    item = Template(**data.model_dump())
    db.add(item)
    db.commit()
    return as_dict(item)

@router.put('/templates/{id_}')
def edit_template(id_: int, data: TemplateInput, db: Session = DB):
    item = require(db, Template, id_)
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return as_dict(item)

@router.delete('/templates/{id_}')
def delete_template(id_: int, db: Session = DB):
    db.delete(require(db, Template, id_))
    db.commit()
    return {'ok': True}

@router.post('/preview')
def preview(data: PreviewInput, db: Session = DB):
    recipient = require(db, Recipient, data.recipient_id)
    try:
        subject, body = render(data.subject, data.body, data.signature, recipient, data.is_html)
        return {'email': recipient.email, 'subject': subject, 'body': body, 'is_html': data.is_html}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

@router.get('/campaigns')
def campaigns(db: Session = DB):
    result = []
    for c in db.scalars(select(Campaign).order_by(Campaign.id.desc())):
        counts = dict(db.execute(select(Delivery.status, func.count(Delivery.id)).where(Delivery.campaign_id == c.id).group_by(Delivery.status)).all())
        result.append({**as_dict(c), 'counts': counts, 'total': sum(counts.values())})
    return result

@router.post('/campaigns', status_code=201)
def create_campaign(data: CampaignInput, db: Session = DB):
    with SEND_LOCK:
        ids = list(dict.fromkeys(data.recipient_ids))
        if len(ids) > data.campaign_limit:
            raise HTTPException(400, 'Le nombre sélectionné dépasse le plafond de la campagne.')
        docs = checked_documents(db, data.document_ids)
        campaign = Campaign(**data.model_dump(exclude={'recipient_ids', 'document_ids'}), document_ids=[d.id for d in docs])
        db.add(campaign)
        db.flush()
        for id_ in ids:
            recipient = require(db, Recipient, id_)
            if recipient.excluded or (not data.simulation and contacted(db, recipient.email)):
                raise HTTPException(409, f'{recipient.email} est exclu ou déjà contacté/réservé.')
            selected_docs = list(docs)
            if recipient.letter_document_id:
                selected_docs = [d for d in selected_docs if d.kind != 'letter']
                letter = require(db, Document, recipient.letter_document_id)
                if letter.id not in [d.id for d in selected_docs]:
                    selected_docs.append(letter)
            checked_documents(db, [d.id for d in selected_docs])
            try:
                subject, body = render(data.subject, data.body, data.signature, recipient, data.is_html)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
            db.add(Delivery(campaign_id=campaign.id, recipient_id=id_, email=recipient.email, entreprise=recipient.entreprise,
                poste=recipient.poste, subject=subject, body=body, is_html=data.is_html, document_ids=[d.id for d in selected_docs]))
        db.commit()
        return as_dict(campaign)

@router.post('/campaigns/{id_}/{action}')
def campaign_action(id_: int, action: str, data: ActionInput, db: Session = DB):
    with SEND_LOCK:
        campaign = require(db, Campaign, id_)
        if action in ('start', 'resume'):
            if campaign.status not in ('draft', 'paused'):
                raise HTTPException(409, 'Cette campagne ne peut pas démarrer dans son état actuel.')
            if not campaign.simulation and not data.confirm:
                raise HTTPException(400, 'Confirmez explicitement les envois réels.')
            if not campaign.simulation:
                account = gmail.status()
                if not account['connected']:
                    raise HTTPException(400, 'Connectez Gmail avant le premier envoi.')
                if campaign.sender_account and campaign.sender_account != account['email']:
                    raise HTTPException(409, 'Reconnectez le compte Gmail initial de cette campagne.')
                campaign.sender_account = account['email']
            for delivery in db.scalars(select(Delivery).where(Delivery.campaign_id == id_, Delivery.status.in_(['draft', 'pending']))):
                if not campaign.simulation and contacted(db, delivery.email, delivery.id):
                    raise HTTPException(409, f'{delivery.email} est déjà contacté ou réservé.')
                delivery.status, delivery.next_attempt_at, delivery.attempts = 'pending', None, 0
            campaign.status, campaign.error = 'running', ''
            campaign.confirmed_at = now()
        elif action == 'pause':
            if campaign.status != 'running':
                raise HTTPException(409, 'La campagne n’est pas en cours.')
            campaign.status = 'paused'
        elif action == 'stop':
            if campaign.status not in ('draft', 'running', 'paused'):
                raise HTTPException(409, 'Cette campagne est déjà terminée.')
            campaign.status = 'cancelled'
            for delivery in db.scalars(select(Delivery).where(Delivery.campaign_id == id_, Delivery.status.in_(['draft', 'pending']))):
                delivery.status = 'cancelled'
        else:
            raise HTTPException(404, 'Action inconnue.')
        db.commit()
        return as_dict(campaign)

@router.post('/campaigns/{id_}/test-send/self')
def test_send(id_: int, data: ActionInput, db: Session = DB):
    # A real test is recorded and paced through the same durable queue.
    with SEND_LOCK:
        if not data.confirm:
            raise HTTPException(400, 'Confirmez cet envoi de test réel.')
        campaign = require(db, Campaign, id_)
        status = gmail.status()
        if not status['connected']:
            raise HTTPException(400, 'Connectez Gmail.')
        source = db.scalar(select(Delivery).where(Delivery.campaign_id == id_).order_by(Delivery.id))
        if not source:
            raise HTTPException(400, 'Aucun message à tester.')
        if db.scalar(select(Delivery.id).join(Campaign).where(Campaign.is_test.is_(True), Delivery.email == status['email'], Delivery.status.in_(['pending', 'in_progress', 'check']))):
            raise HTTPException(409, 'Un test est encore en attente ou à vérifier. Consultez l’historique avant de recommencer.')
        test = Campaign(name=f'Test · {campaign.name}', subject=source.subject, body=source.body, document_ids=source.document_ids,
            is_html=source.is_html, simulation=False, is_test=True, status='running', campaign_limit=1, daily_limit=campaign.daily_limit,
            delay_seconds=campaign.delay_seconds, confirmed_at=now(), sender_account=status['email'])
        db.add(test)
        db.flush()
        db.add(Delivery(campaign_id=test.id, email=status['email'], subject='[TEST] ' + source.subject, body=source.body,
            is_html=source.is_html, document_ids=source.document_ids, status='pending'))
        db.commit()
        return as_dict(test)

def history_rows(db, q='', status='', campaign_id=None, limit=None):
    query = select(Delivery).order_by(Delivery.id.desc())
    if q:
        query = query.where(Delivery.email.contains(q) | Delivery.entreprise.contains(q) | Delivery.subject.contains(q))
    if status:
        query = query.where(Delivery.status == status)
    if campaign_id:
        query = query.where(Delivery.campaign_id == campaign_id)
    if limit is not None:
        query = query.limit(limit)
    names = {c.id: c.name for c in db.scalars(select(Campaign))}
    return [{**as_dict(d), 'campaign_name': names[d.campaign_id]} for d in db.scalars(query)]

@router.get('/history')
def history(q: str = '', status: str = '', campaign_id: int | None = None, db: Session = DB):
    return history_rows(db, q, status, campaign_id)

@router.patch('/history/{id_}/reply')
def toggle_reply(id_: int, db: Session = DB):
    delivery = require(db, Delivery, id_)
    delivery.replied = not delivery.replied
    db.commit()
    return as_dict(delivery)

@router.get('/history/export')
def export_history(q: str = '', status: str = '', campaign_id: int | None = None, db: Session = DB):
    output = io.StringIO(newline='')
    fields = ['email', 'entreprise', 'poste', 'subject', 'sent_at', 'campaign_name', 'status', 'gmail_id', 'error', 'document_ids', 'body', 'replied']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for item in history_rows(db, q, status, campaign_id):
        writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for k, v in item.items()})
    return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename=historique.csv'})

@router.get('/dashboard')
def dashboard(db: Session = DB):
    counts = dict(db.execute(select(Delivery.status, func.count(Delivery.id)).group_by(Delivery.status)).all())
    days = db.execute(select(func.date(Delivery.sent_at), func.count(Delivery.id)).where(Delivery.status == 'sent').group_by(func.date(Delivery.sent_at)).order_by(func.date(Delivery.sent_at).desc()).limit(14)).all()
    return {'recipients': db.scalar(select(func.count(Recipient.id))), 'campaigns': db.scalar(select(func.count(Campaign.id))),
        'counts': counts, 'sent_today': db.scalar(select(func.count(Delivery.id)).where(Delivery.status == 'sent', Delivery.sent_at >= day_start())),
        'daily_used': used_today(db), 'daily_limit': settings(db)['daily_limit'],
        'chart': [{'date': d, 'count': n} for d, n in reversed(days)], 'recent': history_rows(db, limit=8)}

@router.get('/gmail/status')
def gmail_status():
    return gmail.status()

@router.post('/gmail/connect')
def gmail_connect():
    try:
        gmail.connect()
        return {'ok': True}
    except Exception as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else 'Coffre sécurisé indisponible.') from None

@router.post('/gmail/disconnect')
def gmail_disconnect(db: Session = DB):
    with SEND_LOCK:
        try:
            gmail.disconnect()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        for c in db.scalars(select(Campaign).where(Campaign.status == 'running', Campaign.simulation.is_(False))):
            c.status, c.error = 'paused', 'Compte Gmail déconnecté.'
        db.commit()
    return {'ok': True}

@router.get('/settings')
def get_settings(db: Session = DB):
    return settings(db)

@router.put('/settings')
def put_settings(data: SettingsInput, db: Session = DB):
    item = db.get(Setting, 'limits')
    if item:
        item.value = data.model_dump()
    else:
        db.add(Setting(key='limits', value=data.model_dump()))
    db.commit()
    return data
