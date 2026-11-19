"""Frozen initial schema; future model changes need a new migration."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('users',sa.Column('id',sa.String(36),primary_key=True),sa.Column('email',sa.String(254),nullable=False),sa.Column('name',sa.String(100),nullable=False),sa.Column('password_hash',sa.Text,nullable=False),sa.Column('role',sa.String(24),nullable=False),sa.Column('plan',sa.String(24),nullable=False),sa.Column('stripe_customer',sa.String(100),unique=True),sa.Column('stripe_subscription',sa.String(100)),sa.Column('created_at',sa.String(40),nullable=False))
    op.create_index('ix_users_email','users',['email'],unique=True)
    for name in ['sessions','reset_tokens']:
        op.create_table(name,sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('expires_at',sa.Float,nullable=False))
    op.create_index('ix_sessions_user_id','sessions',['user_id'])
    op.create_table('predictions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('drug_name',sa.String(200),nullable=False),sa.Column('protein_name',sa.String(200),nullable=False),sa.Column('smiles',sa.Text,nullable=False),sa.Column('sequence',sa.Text,nullable=False),sa.Column('dataset',sa.String(10),nullable=False),sa.Column('score',sa.Float,nullable=False),sa.Column('model_version',sa.String(100),nullable=False),sa.Column('provenance',sa.JSON,nullable=False),sa.Column('created_at',sa.String(40),nullable=False))
    for column in ['user_id','dataset','created_at']: op.create_index('ix_predictions_'+column,'predictions',[column])
    op.create_table('usage',sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),primary_key=True),sa.Column('month',sa.String(7),primary_key=True),sa.Column('count',sa.Integer,nullable=False))
    plans=op.create_table('plans',sa.Column('id',sa.String(24),primary_key=True),sa.Column('monthly_limit',sa.Integer,nullable=False),sa.Column('price_id',sa.String(100)),sa.Column('description',sa.Text,nullable=False))
    op.create_table('billing_events',sa.Column('id',sa.String(100),primary_key=True),sa.Column('event_type',sa.String(100),nullable=False),sa.Column('created_at',sa.String(40),nullable=False))
    op.create_table('audit',sa.Column('id',sa.String(36),primary_key=True),sa.Column('actor_id',sa.String(36),nullable=False),sa.Column('action',sa.String(100),nullable=False),sa.Column('details',sa.JSON,nullable=False),sa.Column('created_at',sa.String(40),nullable=False))
    op.bulk_insert(plans,[{'id':'free','monthly_limit':25,'description':'25 predictions per calendar month; private history and PDF reports.'},{'id':'researcher','monthly_limit':1000,'description':'1000 predictions per calendar month.'},{'id':'laboratory','monthly_limit':10000,'description':'10000 predictions per calendar month. Shared workspaces are not yet available.'}])

def downgrade():
    for name in ['audit','billing_events','plans','usage','predictions','reset_tokens','sessions','users']: op.drop_table(name)
