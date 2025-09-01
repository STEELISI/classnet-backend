"""extend size for bearer token

Revision ID: de1a4d80354d
Revises: 8dbc7f681fda
Create Date: 2025-09-01 22:44:42.469465

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'de1a4d80354d'
down_revision = '8dbc7f681fda'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'sessions',
        'sso_token',
        existing_type=sa.String(length=256),
        type_=sa.String(length=1024)
        ) 


def downgrade():
    op.alter_column(
        'sessions',
        'sso_token',
        existing_type=sa.String(length=1024),
        type_=sa.String(length=256)
        ) 

