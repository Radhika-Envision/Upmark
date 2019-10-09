"""Add FKs to response history

Revision ID: 31e60f5e005
Revises: 1dbcbe2a1a6
Create Date: 2015-10-12 01:01:29.128495

"""

# revision identifiers, used by Alembic.
revision = '31e60f5e005'
down_revision = '1dbcbe2a1a6'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    op.create_foreign_key(
        'response_history_measure_id_fkey',
        'response_history', 'measure',
        ['measure_id', 'survey_id'],
        ['id', 'survey_id'],
    )
    op.create_foreign_key(
        'response_history_survey_id_fkey',
        'response_history', 'survey',
        ['survey_id'],
        ['id'],
    )
    op.create_foreign_key(
        'response_history_user_id_fkey',
        'response_history', 'appuser',
        ['user_id'],
        ['id'],
    )
    op.create_foreign_key(
        'response_history_assessment_id_fkey',
        'response_history', 'assessment',
        ['assessment_id'],
        ['id'],
    )


def downgrade():
    op.drop_constraint(
        'response_history_assessment_id_fkey',
        'response_history'
    )
    op.drop_constraint(
        'response_history_user_id_fkey',
        'response_history'
    )
    op.drop_constraint(
        'response_history_survey_id_fkey',
        'response_history'
    )
    op.drop_constraint(
        'response_history_measure_id_fkey',
        'response_history'
    )
