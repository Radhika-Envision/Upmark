"""Initial schema

Revision ID: 2ee8262273c
Revises:
Create Date: 2015-06-18 23:50:05.115083

"""

# revision identifiers, used by Alembic.
revision = '2ee8262273c'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

import guid


def upgrade():
    op.create_table('appuser_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('password', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('organisation_id', guid.GUID(), nullable=True),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('assessment_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('organisation_id', guid.GUID(), nullable=True),
        sa.Column('survey_id', guid.GUID(), nullable=True),
        sa.Column('measureset_id', guid.GUID(), nullable=True),
        sa.Column('approval', sa.Text(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('function',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('function_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('measure_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('subprocess_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('intent', sa.Text(), nullable=False),
        sa.Column('inputs', sa.Text(), nullable=False),
        sa.Column('scenario', sa.Text(), nullable=False),
        sa.Column('questions', sa.Text(), nullable=False),
        sa.Column('response_type', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('organisation',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('region', sa.Text(), nullable=False),
        sa.Column('number_of_customers', sa.Integer(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_table('organisation_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('region', sa.Text(), nullable=False),
        sa.Column('number_of_customers', sa.Integer(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('process_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('function_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('response_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('user_id', guid.GUID(), nullable=True),
        sa.Column('assessment_id', guid.GUID(), nullable=True),
        sa.Column('measure_id', guid.GUID(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('not_relevant', sa.Boolean(), nullable=False),
        sa.Column('response_parts', sa.Text(), nullable=False),
        sa.Column('audit_reason', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('subprocess_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('process_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('survey',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('survey_history',
        sa.Column('id'  , guid.GUID(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('changed', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('systemconfig',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('name')
    )
    op.create_table('appuser',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('password', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('organisation_id', guid.GUID(), nullable=True),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_table('measureset',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('survey_id', guid.GUID(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['survey_id'], ['survey.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('process',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('function_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['function_id'], ['function.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('assessment',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('organisation_id', guid.GUID(), nullable=True),
        sa.Column('survey_id', guid.GUID(), nullable=True),
        sa.Column('measureset_id', guid.GUID(), nullable=True),
        sa.Column('approval', sa.Text(), nullable=False),
        sa.Column('created', sa.Date(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['measureset_id'], ['measureset.id'], ),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.ForeignKeyConstraint(['survey_id'], ['survey.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('subprocess',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('process_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['process_id'], ['process.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('measure',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('subprocess_id', guid.GUID(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('intent', sa.Text(), nullable=False),
        sa.Column('inputs', sa.Text(), nullable=False),
        sa.Column('scenario', sa.Text(), nullable=False),
        sa.Column('questions', sa.Text(), nullable=False),
        sa.Column('response_type', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['subprocess_id'], ['subprocess.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('measureset_measure_link',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('measureset_id', guid.GUID(), nullable=True),
        sa.Column('measure_id', guid.GUID(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['measure_id'], ['measure.id'], ),
        sa.ForeignKeyConstraint(['measureset_id'], ['measureset.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('response',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('user_id', guid.GUID(), nullable=True),
        sa.Column('assessment_id', guid.GUID(), nullable=True),
        sa.Column('measure_id', guid.GUID(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('not_relevant', sa.Boolean(), nullable=False),
        sa.Column('response_parts', sa.Text(), nullable=False),
        sa.Column('audit_reason', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessment.id'], ),
        sa.ForeignKeyConstraint(['measure_id'], ['measure.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['appuser.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('response')
    op.drop_table('measureset_measure_link')
    op.drop_table('measure')
    op.drop_table('subprocess')
    op.drop_table('assessment')
    op.drop_table('process')
    op.drop_table('measureset')
    op.drop_table('appuser')
    op.drop_table('systemconfig')
    op.drop_table('survey_history')
    op.drop_table('survey')
    op.drop_table('subprocess_history')
    op.drop_table('response_history')
    op.drop_table('process_history')
    op.drop_table('organisation_history')
    op.drop_table('organisation')
    op.drop_table('measure_history')
    op.drop_table('function_history')
    op.drop_table('function')
    op.drop_table('assessment_history')
    op.drop_table('appuser_history')
