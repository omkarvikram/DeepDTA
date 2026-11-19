from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event, String, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_setup(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
SessionLocal = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(24), default='researcher')
    plan: Mapped[str] = mapped_column(String(24), default='free')
    stripe_customer: Mapped[str | None] = mapped_column(String(100), unique=True)
    stripe_subscription: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[float] = mapped_column(Float)
class ResetToken(Base):
    __tablename__ = 'reset_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    expires_at: Mapped[float] = mapped_column(Float)
class Prediction(Base):
    __tablename__ = 'predictions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    drug_name: Mapped[str] = mapped_column(String(200), default='Unnamed compound')
    protein_name: Mapped[str] = mapped_column(String(200), default='Unnamed protein')
    smiles: Mapped[str] = mapped_column(Text)
    sequence: Mapped[str] = mapped_column(Text)
    dataset: Mapped[str] = mapped_column(String(10), index=True)
    score: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now, index=True)
class Usage(Base):
    __tablename__ = 'usage'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
class Plan(Base):
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    monthly_limit: Mapped[int] = mapped_column(Integer)
    price_id: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
class BillingEvent(Base):
    __tablename__ = 'billing_events'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

def get_db():
    with SessionLocal() as db: yield db
