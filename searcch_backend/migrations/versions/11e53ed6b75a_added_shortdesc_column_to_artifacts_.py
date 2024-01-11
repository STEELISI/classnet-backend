"""added shortdesc column to artifacts table

Revision ID: 11e53ed6b75a
Revises: b855f456a919
Create Date: 2024-01-11 21:07:25.491671

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '11e53ed6b75a'
down_revision = 'b855f456a919'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('artifacts', sa.Column('shortdesc', sa.String(length=1024), nullable=True))

def downgrade():
    op.drop_column('artifacts', 'shortdesc')
