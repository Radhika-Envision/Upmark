"""Removed old survey.is_open flag

Revision ID: 16ecb4a1694
Revises: 3dd68911144
Create Date: 2015-09-14 12:18:36.679306

"""

# revision identifiers, used by Alembic.
revision = '16ecb4a1694'
down_revision = '3dd68911144'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_foreign_key(
        'purchased_survey_survey_id_fkey', 'purchased_survey', 'survey',
        ['survey_id'],
        ['id'])
    op.drop_column('survey', 'open_date')


def downgrade():
    op.add_column('survey', sa.Column('open_date', postgresql.TIMESTAMP()))
    op.drop_constraint(
        'purchased_survey_survey_id_fkey',
        'purchased_survey',
        type_='foreignkey')
