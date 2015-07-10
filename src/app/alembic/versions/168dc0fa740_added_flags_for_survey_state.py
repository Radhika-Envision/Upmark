"""Added flags for survey state

Revision ID: 168dc0fa740
Revises: 1f07439563a
Create Date: 2015-07-10 01:39:38.488713

"""

# revision identifiers, used by Alembic.
revision = '168dc0fa740'
down_revision = '1f07439563a'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('survey', sa.Column('finalised_date', sa.DateTime(), nullable=True))
    op.add_column('survey', sa.Column('open_date', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('survey', 'open_date')
    op.drop_column('survey', 'finalised_date')
