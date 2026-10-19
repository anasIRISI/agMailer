import json
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import make_msgid
from sqlalchemy import select, func, or_
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from app.core.config import TIMEZONE
from app.database.session import SessionLocal, now
from app.models.entities import Campaign, Delivery, Recipient, Document, Setting
from app.repositories.queries import contacted
from app.services.rendering import build_message
from app.services.gmail import gmail

SEND_LOCK = threading.RLock()

def day_start():
    local = datetime.now(ZoneInfo(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)

def used_today(db):
    return db.scalar(select(func.count(Delivery.id)).join(Campaign).where(Campaign.simulation.is_(False),
        Delivery.attempted_at >= day_start(), Delivery.status.in_(['sent', 'check', 'in_progress']))) or 0

def settings(db):
    value = db.get(Setting, 'limits')
    return value.value if value else {'daily_limit': 30, 'delay_seconds': 60}

def recover(db):
    for item in db.scalars(select(Delivery).where(Delivery.status == 'in_progress')):
        item.status = 'check'
        item.error = 'Application interrompue pendant l’envoi. Vérifiez les messages envoyés dans Gmail ; aucune relance automatique.'
    for campaign in db.scalars(select(Campaign).where(Campaign.status == 'running')):
        campaign.status = 'paused'
        campaign.error = 'Envois suspendus après redémarrage. Reprise manuelle nécessaire.'
    db.commit()

def classify_error(exc):
    if not isinstance(exc, HttpError):
        return 'check', 'Connexion interrompue : résultat incertain. Vérifiez Gmail avant toute autre candidature.'
    status = exc.resp.status
    try:
        body = json.loads(exc.content)
        reasons = {entry.get('reason', '') for entry in body.get('error', {}).get('errors', [])}
    except (ValueError, TypeError):
        reasons = set()
    if status in (403, 429) and (status == 429 or reasons & {'dailyLimitExceeded', 'quotaExceeded', 'rateLimitExceeded', 'userRateLimitExceeded'}):
        return 'quota', 'Quota ou limitation Google : campagne suspendue. Vérifiez les restrictions du compte avant de reprendre.'
    if status == 401 or status == 403:
        return 'auth', 'Autorisation Google refusée. Reconnectez Gmail avant de reprendre.'
    if status in (408, 500, 502, 503, 504):
        return 'check', 'Erreur Google : acceptation du message incertaine. Vérifiez Gmail ; aucune relance automatique.'
    return 'failed', f'Google a refusé le message (HTTP {status}).'

class QueueEngine:
    def __init__(self, factory=SessionLocal, transport=gmail):
        self.factory = factory
        self.transport = transport

    def tick(self):
        if not SEND_LOCK.acquire(blocking=False):
            return
        try:
            with self.factory() as db:
                campaigns = list(db.scalars(select(Campaign).where(Campaign.status == 'running').order_by(Campaign.id)))
                for campaign in campaigns:
                    if campaign.next_send_at and campaign.next_send_at > now():
                        continue
                    if self._process(db, campaign):
                        break  # one outbound request per tick, globally
        finally:
            SEND_LOCK.release()

    def _process(self, db, campaign):
        clock = db.get(Setting, 'queue_clock')
        if clock and datetime.fromisoformat(clock.value['next_send_at']) > now():
            return False
        delivery = db.scalar(select(Delivery).where(Delivery.campaign_id == campaign.id, Delivery.status == 'pending',
            or_(Delivery.next_attempt_at.is_(None), Delivery.next_attempt_at <= now())).order_by(Delivery.id).limit(1))
        if not delivery:
            waiting = db.scalar(select(func.count(Delivery.id)).where(Delivery.campaign_id == campaign.id, Delivery.status == 'pending'))
            if not waiting:
                campaign.status = 'completed'
                db.commit()
            return False
        recipient = db.get(Recipient, delivery.recipient_id) if delivery.recipient_id else None
        excluded = db.scalar(select(Recipient.id).where(Recipient.email == delivery.email, Recipient.excluded.is_(True)))
        if excluded or (recipient and recipient.excluded):
            delivery.status, delivery.error = 'cancelled', 'Destinataire dans la liste d’exclusion.'
            db.commit()
            return False
        if not campaign.simulation and not campaign.is_test and contacted(db, delivery.email, delivery.id):
            delivery.status, delivery.error = 'cancelled', 'Adresse déjà contactée ou réservée dans une autre campagne.'
            db.commit()
            return False
        limits = settings(db)
        if not campaign.simulation and used_today(db) >= min(campaign.daily_limit, limits['daily_limit']):
            campaign.status, campaign.error = 'paused', 'Plafond quotidien local atteint. Reprenez manuellement un autre jour.'
            db.commit()
            return False
        try:
            documents = [db.get(Document, id_) for id_ in delivery.document_ids]
            if any(doc is None for doc in documents):
                raise ValueError('Pièce jointe manquante.')
            # Local document validation is distinct from network/authentication preflight.
            delivery.message_id = make_msgid(domain='localhost' if campaign.simulation else 'pfe.local')
            message = build_message(delivery, 'simulation@localhost', documents)
        except (ValueError, OSError) as exc:
            delivery.status, delivery.error = 'failed', str(exc)
            campaign.status, campaign.error = 'paused', 'Corrigez les documents avant de poursuivre.'
            db.commit()
            return False
        try:
            prepared = None if campaign.simulation else self.transport.prepare()
            sender = 'simulation@localhost' if campaign.simulation else prepared[0]
            if not campaign.simulation and campaign.sender_account and sender != campaign.sender_account:
                campaign.status, campaign.error = 'paused', 'Le compte connecté diffère du compte autorisé pour cette campagne.'
                db.commit()
                return False
            delivery.sender = sender
            delivery.message_id = make_msgid(domain=sender.split('@')[-1])
            message = build_message(delivery, sender, documents)
        except (ValueError, RefreshError):
            delivery.error = 'Autorisation Google indisponible. Reconnectez Gmail avant de reprendre.'
            campaign.status, campaign.error = 'paused', delivery.error
            db.commit()
            return False
        except Exception:
            # No send request has started: a bounded retry is safe here.
            delivery.attempts += 1
            delivery.error = 'Connexion ou actualisation Google indisponible avant l’envoi.'
            delivery.next_attempt_at = now() + timedelta(seconds=30 * 2 ** min(delivery.attempts - 1, 4))
            if delivery.attempts >= 3:
                campaign.status, campaign.error = 'paused', 'Connexion Google indisponible après 3 tentatives. Reconnectez Gmail.'
            db.commit()
            return False
        # Commit intent BEFORE touching the external system. A crash becomes 'check' on recovery.
        delivery.status, delivery.attempted_at = 'in_progress', now()
        delivery.attempts += 1
        db.commit()
        try:
            if campaign.simulation:
                delivery.status, delivery.error = 'simulated', ''
            else:
                message_id = self.transport.send(prepared, message)
                if not message_id:
                    raise RuntimeError('Identifiant Gmail absent')
                delivery.gmail_id, delivery.status, delivery.sent_at, delivery.error = message_id, 'sent', now(), ''
        except Exception as exc:
            kind, error = classify_error(exc)
            delivery.error = error
            if kind in ('quota', 'auth'):
                delivery.status = 'pending'
                campaign.status, campaign.error = 'paused', error
                for other in db.scalars(select(Campaign).where(Campaign.simulation.is_(False), Campaign.status == 'running')):
                    other.status, other.error = 'paused', error
            else:
                delivery.status = kind
                if kind == 'check':
                    campaign.status, campaign.error = 'paused', error
        campaign.next_send_at = now() + timedelta(seconds=max(campaign.delay_seconds, limits['delay_seconds']))
        if not campaign.simulation:
            clock_value = {'next_send_at': campaign.next_send_at.isoformat()}
            if clock:
                clock.value = clock_value
            else:
                db.add(Setting(key='queue_clock', value=clock_value))
        # Global pacing across campaigns.
        for other in db.scalars(select(Campaign).where(Campaign.status == 'running')):
            other.next_send_at = campaign.next_send_at
        remaining = db.scalar(select(func.count(Delivery.id)).where(Delivery.campaign_id == campaign.id, Delivery.status == 'pending'))
        if not remaining and campaign.status == 'running':
            campaign.status = 'completed'
        db.commit()
        return True

queue_engine = QueueEngine()
