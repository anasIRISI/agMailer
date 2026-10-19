from sqlalchemy import String, Text, Boolean, ForeignKey, DateTime, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base, now

class Recipient(Base):
    __tablename__ = 'recipients'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    entreprise: Mapped[str] = mapped_column(default='')
    nom_recruteur: Mapped[str] = mapped_column(default='')
    poste: Mapped[str] = mapped_column(default='')
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    letter_document_id: Mapped[int | None] = mapped_column(ForeignKey('documents.id'), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(default='cv')
    size: Mapped[int]
    storage_name: Mapped[str] = mapped_column(unique=True)
    sha256: Mapped[str]
    created_at: Mapped[object] = mapped_column(DateTime, default=now)

class Template(Base):
    __tablename__ = 'templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(Text, default='')
    is_html: Mapped[bool] = mapped_column(default=False)

class Campaign(Base):
    __tablename__ = 'campaigns'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(Text, default='')
    is_html: Mapped[bool] = mapped_column(default=False)
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default='draft', index=True)
    simulation: Mapped[bool] = mapped_column(default=True)
    is_test: Mapped[bool] = mapped_column(default=False)
    sender_account: Mapped[str] = mapped_column(default='')
    daily_limit: Mapped[int] = mapped_column(default=30)
    campaign_limit: Mapped[int] = mapped_column(default=100)
    delay_seconds: Mapped[int] = mapped_column(default=60)
    confirmed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    next_send_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[object] = mapped_column(DateTime, default=now)

class Delivery(Base):
    __tablename__ = 'deliveries'
    __table_args__ = (UniqueConstraint('campaign_id', 'email'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey('campaigns.id'), index=True)
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey('recipients.id'), nullable=True)
    email: Mapped[str] = mapped_column(index=True)
    entreprise: Mapped[str] = mapped_column(default='')
    poste: Mapped[str] = mapped_column(default='')
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    is_html: Mapped[bool] = mapped_column(default=False)
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default='draft', index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    attempted_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    gmail_id: Mapped[str] = mapped_column(default='')
    sender: Mapped[str] = mapped_column(default='')
    message_id: Mapped[str] = mapped_column(default='')
    error: Mapped[str] = mapped_column(Text, default='')
    replied: Mapped[bool] = mapped_column(default=False)

class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
