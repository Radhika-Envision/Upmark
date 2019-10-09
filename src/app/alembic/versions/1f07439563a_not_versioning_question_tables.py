"""Not versioning question tables

Revision ID: 1f07439563a
Revises: 3eb50f40c34
Create Date: 2015-07-10 01:37:00.582608

"""

# revision identifiers, used by Alembic.
revision = '1f07439563a'
down_revision = '3eb50f40c34'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.drop_table('assessment_history')
    op.drop_table('process_history')
    op.drop_table('subprocess_history')
    op.drop_table('function_history')
    op.drop_table('survey_history')
    op.drop_table('measure_history')
    op.drop_column('assessment', 'version')
    op.drop_column('function', 'version')
    op.drop_column('measure', 'version')
    op.drop_column('process', 'version')
    op.drop_column('subprocess', 'version')
    op.drop_column('survey', 'version')


def downgrade():
    op.add_column('survey', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('subprocess', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('process', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('measure', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('function', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('assessment', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.create_table('measure_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('subprocess_id', postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('weight', postgresql.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False),
        sa.Column('intent', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('inputs', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('scenario', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('questions', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('response_type', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('survey_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', 'version', name='measure_history_pkey')
    )
    op.create_table('survey_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', 'version', name='survey_history_pkey')
    )
    op.create_table('function_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('description', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('survey_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', 'version', name='function_history_pkey')
    )
    op.create_table('subprocess_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('process_id', postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('description', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('survey_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', 'version', name='subprocess_history_pkey')
    )
    op.create_table('process_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('function_id', postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column('seq', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('title', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('description', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('survey_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', 'version', name='process_history_pkey')
    )
    op.create_table('assessment_history',
        sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('organisation_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('survey_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('measureset_id', postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column('approval', sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', 'version', name='assessment_history_pkey')
    )
