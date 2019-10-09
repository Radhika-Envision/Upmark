"""Flexible tree structure for survey objects

Revision ID: 28d059146a6
Revises: 50bc8721abe
Create Date: 2015-08-01 04:21:15.328982

"""

# revision identifiers, used by Alembic.
revision = '28d059146a6'
down_revision = '50bc8721abe'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import old_deps.guid as guid

def upgrade():
    op.create_table('hierarchy',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('survey_id', guid.GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('structure', postgresql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            name='hierarchy_survey_id_fkey'),
        sa.PrimaryKeyConstraint('id', 'survey_id')
    )
    op.create_table('qnode',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('survey_id', guid.GUID(), nullable=False),
        sa.Column('hierarchy_id', guid.GUID()),
        sa.Column('parent_id', guid.GUID()),
        sa.Column('seq', sa.Integer()),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id'],
            name='qnode_hierarchy_id_fkey'),
        sa.ForeignKeyConstraint(
            ['parent_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id'],
            name='qnode_parent_id_fkey'),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            name='qnode_survey_id_fkey'),
        sa.CheckConstraint(
            '(parent_id IS NULL AND hierarchy_id IS NOT NULL) OR '
            '(parent_id IS NOT NULL AND hierarchy_id IS NULL)',
            name='qnode_root_check'),
        sa.PrimaryKeyConstraint('id', 'survey_id')
    )
    op.create_table('qnode_measure_link',
        sa.Column('survey_id', guid.GUID(), nullable=False),
        sa.Column('qnode_id', guid.GUID(), nullable=False),
        sa.Column('measure_id', guid.GUID(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id'],
            name='qnode_measure_link_measure_id_fkey'),
        sa.ForeignKeyConstraint(
            ['qnode_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id'],
            name='qnode_measure_link_qnode_id_fkey'),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            name='qnode_measure_link_survey_id_fkey'),
        sa.PrimaryKeyConstraint('survey_id', 'qnode_id', 'measure_id')
    )

    op.add_column(
        'assessment', sa.Column('hierarchy_id', guid.GUID(), nullable=False))
    op.drop_constraint(
        'assessment_measureset_id_fkey', 'assessment', type_='foreignkey')
    op.create_foreign_key(
        'assessment_hierarchy_id_fkey', 'assessment', 'hierarchy',
        ['hierarchy_id', 'survey_id'],
        ['id', 'survey_id'])
    op.drop_column('assessment', 'measureset_id')
    op.drop_constraint(
        'measure_subprocess_id_fkey', 'measure', type_='foreignkey')
    op.create_foreign_key(
        'measure_survey_id_fkey', 'measure', 'survey',
        ['survey_id'],
        ['id'])
    op.drop_column('measure', 'seq')
    op.drop_column('measure', 'subprocess_id')
    op.add_column(
        'survey', sa.Column('description', sa.Text()))

    op.drop_table('measureset_measure_link')
    op.drop_table('measureset')
    op.drop_table('subprocess')
    op.drop_table('process')
    op.drop_table('function')


def downgrade():
    op.create_table('function',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('survey_id', postgresql.UUID(), nullable=False),
        sa.Column('seq', sa.INTEGER()),
        sa.Column('title', sa.TEXT(), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            name='function_survey_id_fkey'),
        sa.PrimaryKeyConstraint(
            'id', 'survey_id', name='function_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table('process',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('survey_id', postgresql.UUID(), nullable=False),
        sa.Column('function_id', postgresql.UUID()),
        sa.Column('seq', sa.INTEGER()),
        sa.Column('title', sa.TEXT(), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(
            ['function_id', 'survey_id'],
            ['function.id', 'function.survey_id'],
            name='process_function_id_fkey'),
        sa.PrimaryKeyConstraint(
            'id', 'survey_id', name='process_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table('subprocess',
        sa.Column('id', postgresql.UUID(),  nullable=False),
        sa.Column('survey_id', postgresql.UUID(), nullable=False),
        sa.Column('process_id', postgresql.UUID()),
        sa.Column('seq', sa.INTEGER()),
        sa.Column('title', sa.TEXT(), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(
            ['process_id', 'survey_id'],
            ['process.id', 'process.survey_id'],
            name='subprocess_process_id_fkey'),
        sa.PrimaryKeyConstraint(
            'id', 'survey_id', name='subprocess_pkey'),
        postgresql_ignore_search_path=False
    )
    op.create_table('measureset',
        sa.Column('id', postgresql.UUID(),  nullable=False),
        sa.Column('survey_id', postgresql.UUID(), nullable=False),
        sa.Column('title', sa.TEXT(),  nullable=False),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id'],
            name='measureset_survey_id_fkey'),
        sa.PrimaryKeyConstraint(
            'id', 'survey_id', name='measureset_pkey')
    )
    op.create_table('measureset_measure_link',
        sa.Column('survey_id', postgresql.UUID(), nullable=False),
        sa.Column('measureset_id', postgresql.UUID(), nullable=False),
        sa.Column('measure_id', postgresql.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id'],
            name='measureset_measure_link_measure_id_fkey'),
        sa.ForeignKeyConstraint(
            ['measureset_id', 'survey_id'],
            ['measureset.id', 'measureset.survey_id'],
            name='measureset_measure_link_measureset_id_fkey')
    )

    op.drop_column(
        'survey', 'description')
    op.add_column(
        'measure', sa.Column('subprocess_id', postgresql.UUID()))
    op.add_column(
        'measure', sa.Column('seq', sa.INTEGER()))
    op.drop_constraint(
        'measure_survey_id_fkey', 'measure', type_='foreignkey')
    op.create_foreign_key(
        'measure_subprocess_id_fkey', 'measure', 'subprocess',
        ['subprocess_id', 'survey_id'],
        ['id', 'survey_id'])
    op.add_column(
        'assessment', sa.Column(
            'measureset_id', postgresql.UUID(), nullable=False))
    op.drop_constraint(
        'assessment_hierarchy_id_fkey', 'assessment', type_='foreignkey')
    op.create_foreign_key(
        'assessment_measureset_id_fkey', 'assessment', 'measureset',
        ['measureset_id', 'survey_id'],
        ['id', 'survey_id'])
    op.drop_column('assessment', 'hierarchy_id')

    op.drop_table('qnode_measure_link')
    op.drop_table('qnode')
    op.drop_table('hierarchy')
