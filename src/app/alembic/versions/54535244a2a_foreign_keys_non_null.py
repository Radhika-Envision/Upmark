"""Foreign keys non-null

Revision ID: 54535244a2a
Revises: 19526f402bf
Create Date: 2015-07-08 23:41:38.765781

"""

# revision identifiers, used by Alembic.
revision = '54535244a2a'
down_revision = '19526f402bf'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.alter_column('assessment_history', 'measureset_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('assessment_history', 'organisation_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('assessment_history', 'survey_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('measureset', 'survey_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('response_history', 'assessment_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('response_history', 'measure_id',
               existing_type=postgresql.UUID(),
               nullable=False)
    op.alter_column('response_history', 'user_id',
               existing_type=postgresql.UUID(),
               nullable=False)


def downgrade():
    op.alter_column('response_history', 'user_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('response_history', 'measure_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('response_history', 'assessment_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('measureset', 'survey_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('assessment_history', 'survey_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('assessment_history', 'organisation_id',
               existing_type=postgresql.UUID(),
               nullable=True)
    op.alter_column('assessment_history', 'measureset_id',
               existing_type=postgresql.UUID(),
               nullable=True)
