"""add indexes

Revision ID: 1140594c2c9
Revises: 50058a07f33
Create Date: 2015-10-27 04:17:57.833500

"""

# revision identifiers, used by Alembic.
revision = '1140594c2c9'
down_revision = '50058a07f33'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_index(
        'appuser_name_index',
        'appuser',
        ['name'], unique=False)
    
    op.create_index(
        'survey_tracking_id_index',
        'survey',
        ['tracking_id'], unique=False)
    op.create_index(
        'survey_created_index',
        'survey',
        ['created'], unique=False)
    
    op.create_index(
        'qnode_parent_id_survey_id_index',
        'qnode',
        ['parent_id', 'survey_id'], unique=False)
    op.create_index(
        'qnode_hierarchy_id_survey_id_index',
        'qnode',
        ['hierarchy_id', 'survey_id'], unique=False)

    op.create_index(
        'qnodemeasure_qnode_id_survey_id_index',
        'qnode_measure_link',
        ['qnode_id', 'survey_id'], unique=False)
    op.create_index(
        'qnodemeasure_measure_id_survey_id_index',
        'qnode_measure_link',
        ['measure_id', 'survey_id'], unique=False)

    op.create_index(
        'assessment_organisation_id_hierarchy_id_index',
        'assessment',
        ['organisation_id', 'hierarchy_id'], unique=False)

    op.create_index(
        'rnode_qnode_id_assessment_id_index',
        'rnode',
        ['qnode_id', 'assessment_id'], unique=False)

    op.create_index(
        'response_assessment_id_measure_id_index',
        'response',
        ['assessment_id', 'measure_id'], unique=False)


def downgrade():
    op.drop_index('appuser_name_index',
                  table_name='appuser')
    op.drop_index('survey_tracking_id_index',
                  table_name='survey')
    op.drop_index('survey_created_index',
                  table_name='survey')
    op.drop_index('purchasedsurvey_open_date_index',
                  table_name='purchased_survey')
    op.drop_index('qnode_hierarchy_id_survey_id_index',
                  table_name='qnode')
    op.drop_index('qnode_parent_id_survey_id_index',
                  table_name='qnode')
    op.drop_index('qnodemeasure_measure_id_survey_id_index',
                  table_name='qnode_measure_link')
    op.drop_index('qnodemeasure_qnode_id_survey_id_index',
                  table_name='qnode_measure_link')
    op.drop_index('assessment_organisation_id_hierarchy_id_index',
                  table_name='assessment')
    op.drop_index('rnode_qnode_id_assessment_id_index',
                  table_name='rnode')
    op.drop_index('response_assessment_id_measure_id_index',
                  table_name='response')

