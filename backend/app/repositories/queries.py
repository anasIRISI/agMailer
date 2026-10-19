from sqlalchemy import select
from app.models.entities import Delivery, Campaign

RESERVED = ('pending', 'in_progress', 'sent', 'check')

def contacted(db, email, exclude_id=None):
    q = select(Delivery).join(Campaign).where(Delivery.email == email, Campaign.simulation.is_(False), Campaign.is_test.is_(False), Delivery.status.in_(RESERVED))
    if exclude_id is not None:
        q = q.where(Delivery.id != exclude_id)
    return db.scalar(q.limit(1)) is not None

def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
