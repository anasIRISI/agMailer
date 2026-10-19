import json
from datetime import timedelta
import pytest
from httplib2 import Response
from googleapiclient.errors import HttpError
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base, now
from app.models.entities import Recipient, Campaign, Delivery, Setting
from app.services.queue import QueueEngine, recover

class Transport:
    def __init__(self, error=None, prepare_error=None):
        self.calls = []
        self.error = error
        self.prepare_error = prepare_error
    def prepare(self):
        if self.prepare_error:
            raise self.prepare_error
        return 'anas@example.com', None
    def send(self, prepared, message):
        self.calls.append(message)
        if self.error:
            raise self.error
        return 'gmail-123'

def seed(db, simulation=False, email='rh@example.com'):
    r = Recipient(email=email)
    db.add(r)
    db.flush()
    c = Campaign(name='PFE', subject='PFE', body='Bonjour', simulation=simulation, status='running', delay_seconds=10)
    db.add(c)
    db.flush()
    d = Delivery(campaign_id=c.id, recipient_id=r.id, email=r.email, subject='PFE', body='Bonjour', status='pending')
    db.add(d)
    db.commit()
    return c, d

def refresh(db, *items):
    db.expire_all()
    for item in items:
        db.refresh(item)

def test_real_send_saved_once(factory, db):
    c, d = seed(db)
    transport = Transport()
    worker = QueueEngine(factory, transport)
    worker.tick()
    refresh(db, d)
    assert d.status == 'sent' and d.gmail_id == 'gmail-123'
    assert d.message_id and d.attempted_at
    worker.tick()
    assert len(transport.calls) == 1

def test_simulation_never_calls_google(factory, db):
    c, d = seed(db, simulation=True)
    transport = Transport(prepare_error=RuntimeError('must not call'))
    QueueEngine(factory, transport).tick()
    refresh(db, d)
    assert d.status == 'simulated' and not transport.calls

def test_daily_limit_pauses(factory, db):
    c, d = seed(db)
    db.add(Setting(key='limits', value={'daily_limit': 1, 'delay_seconds': 10}))
    db.add(Delivery(campaign_id=c.id, email='previous@example.com', subject='PFE', body='Hi', status='sent', attempted_at=now(), sent_at=now()))
    db.commit()
    t = Transport()
    QueueEngine(factory, t).tick()
    refresh(db, c, d)
    assert c.status == 'paused' and d.status == 'pending' and not t.calls

@pytest.mark.parametrize('error,status', [(TimeoutError(), 'check'), (HttpError(Response({'status':'503'}), b'{}'), 'check'), (HttpError(Response({'status':'400'}), b'{}'), 'failed')])
def test_errors_do_not_resend(factory, db, error, status):
    c, d = seed(db)
    t = Transport(error)
    worker = QueueEngine(factory, t)
    worker.tick()
    refresh(db, d)
    assert d.status == status
    worker.tick()
    assert len(t.calls) == 1

def test_quota_stops_campaign(factory, db):
    c, d = seed(db)
    other, _ = seed(db, email='other@example.com')
    error = HttpError(Response({'status':'403'}), json.dumps({'error': {'errors': [{'reason': 'dailyLimitExceeded'}]}}).encode())
    t = Transport(error)
    QueueEngine(factory, t).tick()
    refresh(db, c, d, other)
    assert c.status == 'paused' and d.status == 'pending'
    assert other.status == 'paused'
    assert 'Quota' in c.error

def test_bounded_preflight_backoff(factory, db):
    c, d = seed(db)
    t = Transport(prepare_error=OSError('offline'))
    worker = QueueEngine(factory, t)
    for i in range(3):
        worker.tick()
        refresh(db, d)
        assert d.next_attempt_at > now()
        d.next_attempt_at = now() - timedelta(seconds=1)
        db.commit()
    refresh(db, c)
    assert c.status == 'paused' and not t.calls

def test_persistent_recovery(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'test.sqlite3'))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        c, d = seed(db)
        d.status = 'in_progress'
        db.commit()
    engine.dispose()
    with factory() as db:
        recover(db)
        assert db.get(Campaign, c.id).status == 'paused'
        assert db.get(Delivery, d.id).status == 'check'

def test_exclusion_at_send_time(factory, db):
    c, d = seed(db)
    db.get(Recipient, d.recipient_id).excluded = True
    db.commit()
    t = Transport()
    QueueEngine(factory, t).tick()
    refresh(db, d)
    assert d.status == 'cancelled' and not t.calls

def test_duplicate_guard(factory, db):
    c, d = seed(db)
    other = Campaign(name='Previous', subject='PFE', body='Body', simulation=False)
    db.add(other)
    db.flush()
    db.add(Delivery(campaign_id=other.id, email=d.email, subject='PFE', body='Body', status='sent'))
    db.commit()
    t = Transport()
    QueueEngine(factory, t).tick()
    refresh(db, d)
    assert d.status == 'cancelled' and not t.calls

def test_global_pacing_new_campaign(factory, db):
    c, d = seed(db)
    t = Transport()
    worker = QueueEngine(factory, t)
    worker.tick()
    seed(db, email='another@example.com')
    worker.tick()
    assert len(t.calls) == 1

def test_account_switch_is_paused(factory, db):
    c, d = seed(db)
    c.sender_account = 'old@example.com'
    db.commit()
    t = Transport()
    QueueEngine(factory, t).tick()
    refresh(db, c, d)
    assert c.status == 'paused' and d.status == 'pending' and not t.calls
