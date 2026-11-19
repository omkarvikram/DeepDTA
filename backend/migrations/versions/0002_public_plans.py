"""Add public INR plan catalogue; retain older plans for existing accounts."""
from alembic import op
import sqlalchemy as sa

revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    plans=sa.table('plans',sa.column('id',sa.String),sa.column('monthly_limit',sa.Integer),sa.column('description',sa.Text))
    op.bulk_insert(plans,[
        {'id':'plus','monthly_limit':100,'description':'100 prediction credits each month, saved history and PDF reports.'},
        {'id':'pro','monthly_limit':300,'description':'300 prediction credits each month for larger screening runs.'},
        {'id':'ultra','monthly_limit':800,'description':'800 prediction credits each month for frequent research screening.'},
    ])

def downgrade():
    op.execute("DELETE FROM plans WHERE id IN ('plus','pro','ultra')")
