"""Composite PKs for question hierarchy

Revision ID: 412f89c7d08
Revises: 168dc0fa740
Create Date: 2015-07-11 12:21:45.352281

"""

# revision identifiers, used by Alembic.
revision = '412f89c7d08'
down_revision = '168dc0fa740'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

import old_deps.guid as guid


def upgrade():
    op.drop_column('measureset_measure_link', 'id')

    op.drop_constraint(
        'assessment_measureset_id_fkey',
        'assessment', type_='foreignkey')
    op.drop_constraint(
        'response_measure_id_fkey',
        'response', type_='foreignkey')
    op.drop_constraint(
        'measure_survey_id_fkey',
        'measure', type_='foreignkey')
    op.drop_constraint(
        'measure_subprocess_id_fkey',
        'measure', type_='foreignkey')
    op.drop_constraint(
        'measureset_measure_link_survey_id_fkey',
        'measureset_measure_link', type_='foreignkey')
    op.drop_constraint(
        'measureset_measure_link_measureset_id_fkey',
        'measureset_measure_link', type_='foreignkey')
    op.drop_constraint(
        'measureset_measure_link_measure_id_fkey',
        'measureset_measure_link', type_='foreignkey')
    op.drop_constraint(
        'process_function_id_fkey',
        'process', type_='foreignkey')
    op.drop_constraint(
        'process_survey_id_fkey',
        'process', type_='foreignkey')
    op.drop_constraint(
        'subprocess_survey_id_fkey',
        'subprocess', type_='foreignkey')
    op.drop_constraint(
        'subprocess_process_id_fkey',
        'subprocess', type_='foreignkey')

    op.drop_constraint('measureset_pkey', 'measureset', type_='primary')
    op.drop_constraint('measure_pkey', 'measure', type_='primary')
    op.drop_constraint('subprocess_pkey', 'subprocess', type_='primary')
    op.drop_constraint('process_pkey', 'process', type_='primary')
    op.drop_constraint('function_pkey', 'function', type_='primary')

    op.add_column('response', sa.Column(
        'survey_id', guid.GUID, nullable=False))
    op.add_column('response_history', sa.Column(
        'survey_id', guid.GUID, nullable=False))

    op.create_primary_key('function_pkey', 'function', ['id', 'survey_id'])
    op.create_primary_key('process_pkey', 'process', ['id', 'survey_id'])
    op.create_primary_key('subprocess_pkey', 'subprocess', ['id', 'survey_id'])
    op.create_primary_key('measure_pkey', 'measure', ['id', 'survey_id'])
    op.create_primary_key('measureset_pkey', 'measureset', ['id', 'survey_id'])

    op.create_foreign_key(
        'assessment_measureset_id_fkey',
        'assessment', 'measureset',
        ['measureset_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'response_survey_id_fkey',
        'response', 'survey',
        ['survey_id'],
        ['id'])
    op.create_foreign_key(
        'response_measure_id_fkey',
        'response', 'measure',
        ['measure_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'measure_subprocess_id_fkey',
        'measure', 'subprocess',
        ['subprocess_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'measureset_measure_link_measure_id_fkey',
        'measureset_measure_link', 'measure',
        ['measure_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'measureset_measure_link_measureset_id_fkey',
        'measureset_measure_link', 'measureset',
        ['measureset_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'process_function_id_fkey',
        'process', 'function',
        ['function_id', 'survey_id'],
        ['id', 'survey_id'])
    op.create_foreign_key(
        'subprocess_process_id_fkey',
        'subprocess', 'process',
        ['process_id', 'survey_id'],
        ['id', 'survey_id'])


def downgrade():
    op.drop_constraint(
        'subprocess_process_id_fkey',
        'subprocess', type_='foreignkey')
    op.drop_constraint(
        'process_function_id_fkey',
        'process', type_='foreignkey')
    op.drop_constraint(
        'measureset_measure_link_measureset_id_fkey',
        'measureset_measure_link', type_='foreignkey')
    op.drop_constraint(
        'measureset_measure_link_measure_id_fkey',
        'measureset_measure_link', type_='foreignkey')
    op.drop_constraint(
        'measure_subprocess_id_fkey',
        'measure', type_='foreignkey')
    op.drop_constraint(
        'response_measure_id_fkey',
        'response', type_='foreignkey')
    op.drop_constraint(
        'response_survey_id_fkey',
        'response', type_='foreignkey')
    op.drop_constraint(
        'assessment_measureset_id_fkey',
        'assessment', type_='foreignkey')

    op.drop_constraint('measureset_pkey', 'measureset', type_='primary')
    op.drop_constraint('measure_pkey', 'measure', type_='primary')
    op.drop_constraint('subprocess_pkey', 'subprocess', type_='primary')
    op.drop_constraint('process_pkey', 'process', type_='primary')
    op.drop_constraint('function_pkey', 'function', type_='primary')

    op.drop_column('response_history', 'survey_id')
    op.drop_column('response', 'survey_id')

    op.create_primary_key('function_pkey', 'function', ['id'])
    op.create_primary_key('process_pkey', 'process', ['id'])
    op.create_primary_key('subprocess_pkey', 'subprocess', ['id'])
    op.create_primary_key('measure_pkey', 'measure', ['id'])
    op.create_primary_key('measureset_pkey', 'measureset', ['id'])

    op.create_foreign_key(
        'subprocess_process_id_fkey',
        'subprocess', 'process',
        ['process_id'], ['id'])
    op.create_foreign_key(
        'subprocess_survey_id_fkey',
        'subprocess', 'survey',
        ['survey_id'], ['id'])
    op.create_foreign_key(
        'process_survey_id_fkey',
        'process', 'survey',
        ['survey_id'], ['id'])
    op.create_foreign_key(
        'process_function_id_fkey',
        'process', 'function',
        ['function_id'], ['id'])
    op.create_foreign_key(
        'measureset_measure_link_measure_id_fkey',
        'measureset_measure_link', 'measure',
        ['measure_id'], ['id'])
    op.create_foreign_key(
        'measureset_measure_link_measureset_id_fkey',
        'measureset_measure_link', 'measureset',
        ['measureset_id'], ['id'])
    op.create_foreign_key(
        'measureset_measure_link_survey_id_fkey',
        'measureset_measure_link', 'survey',
        ['survey_id'], ['id'])
    op.create_foreign_key(
        'measure_subprocess_id_fkey',
        'measure', 'subprocess',
        ['subprocess_id'], ['id'])
    op.create_foreign_key(
        'measure_survey_id_fkey',
        'measure', 'survey',
        ['survey_id'], ['id'])
    op.create_foreign_key(
        'response_measure_id_fkey',
        'response', 'measure',
        ['measure_id'], ['id'])
    op.create_foreign_key(
        'assessment_measureset_id_fkey',
        'assessment', 'measureset',
        ['measureset_id'], ['id'])

    op.add_column('measureset_measure_link', sa.Column(
        'id', sa.INTEGER(), nullable=False))
