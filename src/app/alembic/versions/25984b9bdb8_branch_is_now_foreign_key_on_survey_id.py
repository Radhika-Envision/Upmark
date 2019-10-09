"""Branch is now foreign key on survey ID

Revision ID: 25984b9bdb8
Revises: 2c77b7a9033
Create Date: 2015-07-08 01:03:58.792359

"""

# revision identifiers, used by Alembic.
revision = '25984b9bdb8'
down_revision = '2c77b7a9033'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

import old_deps.guid as guid

def upgrade():
    op.add_column('function', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.create_foreign_key(None, 'function', 'survey', ['survey_id'], ['id'])
    op.drop_column('function', 'branch')
    op.add_column('function_history', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.drop_column('function_history', 'branch')
    op.add_column('measure', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.create_foreign_key(None, 'measure', 'survey', ['survey_id'], ['id'])
    op.add_column('measure_history', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.drop_column('measureset', 'branch')
    op.add_column('measureset_measure_link', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.create_foreign_key(None, 'measureset_measure_link', 'survey', ['survey_id'], ['id'])
    op.drop_column('measureset_measure_link', 'version')
    op.drop_column('measureset_measure_link', 'branch')
    op.add_column('process', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.create_foreign_key(None, 'process', 'survey', ['survey_id'], ['id'])
    op.drop_column('process', 'branch')
    op.add_column('process_history', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.drop_column('process_history', 'branch')
    op.add_column('subprocess', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.create_foreign_key(None, 'subprocess', 'survey', ['survey_id'], ['id'])
    op.drop_column('subprocess', 'branch')
    op.add_column('subprocess_history', sa.Column('survey_id', guid.GUID(), nullable=False))
    op.drop_column('subprocess_history', 'branch')
    op.drop_column('survey', 'branch')
    op.drop_column('survey_history', 'branch')

    op.alter_column('measureset_measure_link', 'measureset_id', nullable=False)
    op.alter_column('measureset_measure_link', 'measure_id', nullable=False)
    op.alter_column('response', 'user_id', nullable=False)
    op.alter_column('response', 'measure_id', nullable=False)
    op.alter_column('response', 'assessment_id', nullable=False)
    op.alter_column('assessment', 'organisation_id', nullable=False)
    op.alter_column('assessment', 'survey_id', nullable=False)
    op.alter_column('assessment', 'measureset_id', nullable=False)


def downgrade():
    op.alter_column('assessment', 'measureset_id', nullable=True)
    op.alter_column('assessment', 'survey_id', nullable=True)
    op.alter_column('assessment', 'organisation_id', nullable=True)
    op.alter_column('response', 'assessment_id', nullable=True)
    op.alter_column('response', 'measure_id', nullable=True)
    op.alter_column('response', 'user_id', nullable=True)
    op.alter_column('measureset_measure_link', 'measure_id', nullable=True)
    op.alter_column('measureset_measure_link', 'measureset_id', nullable=True)

    op.add_column('survey_history', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.add_column('survey', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.add_column('subprocess_history', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_column('subprocess_history', 'survey_id')
    op.add_column('subprocess', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_constraint('subprocess_survey_id_fkey', 'subprocess', type_='foreignkey')
    op.drop_column('subprocess', 'survey_id')
    op.add_column('process_history', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_column('process_history', 'survey_id')
    op.add_column('process', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_constraint('process_survey_id_fkey', 'process', type_='foreignkey')
    op.drop_column('process', 'survey_id')
    op.add_column('measureset_measure_link', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.add_column('measureset_measure_link', sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False))
    op.drop_constraint('measureset_measure_link_survey_id_fkey', 'measureset_measure_link', type_='foreignkey')
    op.drop_column('measureset_measure_link', 'survey_id')
    op.add_column('measureset', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_column('measure_history', 'survey_id')
    op.drop_constraint('measure_survey_id_fkey', 'measure', type_='foreignkey')
    op.drop_column('measure', 'survey_id')
    op.add_column('function_history', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_column('function_history', 'survey_id')
    op.add_column('function', sa.Column('branch', sa.Text, autoincrement=False, nullable=False))
    op.drop_constraint('function_survey_id_fkey', 'function', type_='foreignkey')
    op.drop_column('function', 'survey_id')
