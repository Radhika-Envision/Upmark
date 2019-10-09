"""Added missing constraints and indexes

Revision ID: f49cdcc1b233
Revises: 151aa56ffd8
Create Date: 2017-06-09 09:13:35.664798

"""

# revision identifiers, used by Alembic.
revision = 'f49cdcc1b233'
down_revision = '151aa56ffd8'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_check_constraint(
        'org_meta_asset_types_check', 'org_meta',
        """asset_types <@ ARRAY[
            'water wholesale', 'water local',
            'wastewater wholesale', 'wastewater local'
        ]::varchar[]""")
    op.create_check_constraint(
        'activity_verbs_check', 'activity',
        """verbs <@ ARRAY[
            'broadcast',
            'create', 'update', 'state', 'delete', 'undelete',
            'relation', 'reorder_children'
        ]::varchar[]""")

    op.create_foreign_key(
        'measure_variable_survey_fk', 'measure_variable', 'survey',
        ['survey_id', 'program_id'],
        ['id', 'program_id'])
    op.create_index(
        'rnode_qnode_id_submission_id_index', 'rnode',
        ['qnode_id', 'submission_id'], unique=False)


def downgrade():
    op.drop_index(
        'rnode_qnode_id_submission_id_index', table_name='rnode')
    op.drop_constraint(
        'measure_variable_survey_fk', 'measure_variable', type_='foreignkey')

    op.drop_constraint('activity_verbs_check', 'activity', type_='check')
    op.drop_constraint('org_meta_asset_types_check', 'org_meta', type_='check')
