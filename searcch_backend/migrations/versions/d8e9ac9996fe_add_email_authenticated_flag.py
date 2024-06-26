"""add_email_authenticated_flag

Revision ID: d8e9ac9996fe
Revises: 697db3d1f50e
Create Date: 2023-08-10 13:32:02.083683

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd8e9ac9996fe'
down_revision = '697db3d1f50e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('persons', sa.Column('emailAuthenticated', sa.Boolean(), nullable=True))
    op.execute('UPDATE "persons" SET "emailAuthenticated" = TRUE WHERE id IN (1433, 1434);') #these ids are for the automatic-imports@cyberexperimentation.org persons which are present in the empty dumpfile
    
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('persons', 'emailAuthenticated')

    # ### end Alembic commands ###
