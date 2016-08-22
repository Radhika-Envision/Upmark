"""Renamed survey to program and hierarchy to survey

Revision ID: 1ef306add5e
Revises: 4959ae79bed
Create Date: 2016-08-17 07:56:28.677973

"""

# revision identifiers, used by Alembic.
revision = '1ef306add5e'
down_revision = '4959ae79bed'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.rename_table('survey', 'program')
    op.execute('ALTER INDEX survey_pkey RENAME TO program_pkey')
    op.execute('ALTER INDEX survey_created_index RENAME TO program_created_index')
    op.execute('ALTER INDEX survey_tracking_id_index RENAME TO program_tracking_id_index')

    op.rename_table('hierarchy', 'survey')
    op.execute('ALTER INDEX hierarchy_pkey RENAME TO survey_pkey')
    op.execute('ALTER TABLE survey RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE survey RENAME CONSTRAINT hierarchy_survey_id_fkey TO survey_program_id_fkey')

    op.rename_table('assessment', 'submission')
    op.execute('ALTER INDEX assessment_pkey RENAME TO submission_pkey')
    op.execute('ALTER INDEX assessment_organisation_id_hierarchy_id_index RENAME TO submission_organisation_id_survey_id_index')
    op.execute('ALTER TABLE submission RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE submission RENAME COLUMN hierarchy_id TO survey_id')
    op.execute('ALTER TABLE submission RENAME CONSTRAINT assessment_approval_check TO submission_approval_check')
    op.execute('ALTER TABLE submission RENAME CONSTRAINT assessment_organisation_id_fkey TO submission_organisation_id_fkey')
    op.execute('ALTER TABLE submission RENAME CONSTRAINT assessment_survey_id_fkey TO submission_program_id_fkey')
    op.execute('ALTER TABLE submission RENAME CONSTRAINT assessment_hierarchy_id_fkey TO submission_survey_id_fkey')

    op.execute('ALTER TABLE measure RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE measure RENAME CONSTRAINT measure_survey_id_fkey TO measure_program_id_fkey')

    op.execute('ALTER TABLE purchased_survey RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE purchased_survey RENAME COLUMN hierarchy_id TO survey_id')
    op.execute('ALTER TABLE purchased_survey RENAME CONSTRAINT purchased_survey_survey_id_fkey TO purchased_survey_program_id_fkey')
    op.execute('ALTER TABLE purchased_survey RENAME CONSTRAINT purchased_survey_hierarchy_id_fkey TO purchased_survey_survey_id_fkey')

    op.execute('ALTER INDEX qnodemeasure_measure_id_survey_id_index RENAME TO qnodemeasure_measure_id_program_id_index')
    op.execute('ALTER INDEX qnodemeasure_qnode_id_survey_id_index RENAME TO qnodemeasure_qnode_id_program_id_index')
    op.execute('ALTER TABLE qnode_measure_link RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE qnode_measure_link RENAME CONSTRAINT qnode_measure_link_survey_id_fkey TO qnode_measure_link_program_id_fkey')

    op.execute('ALTER INDEX qnode_parent_id_survey_id_index RENAME TO qnode_parent_id_program_id_index')
    op.execute('ALTER INDEX qnode_hierarchy_id_survey_id_index RENAME TO qnode_survey_id_program_id_index')
    op.execute('ALTER TABLE qnode RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE qnode RENAME COLUMN hierarchy_id TO survey_id')
    op.execute('ALTER TABLE qnode RENAME CONSTRAINT qnode_survey_id_fkey TO qnode_program_id_fkey')
    op.execute('ALTER TABLE qnode RENAME CONSTRAINT qnode_hierarchy_id_fkey TO qnode_survey_id_fkey')

    op.execute('ALTER TABLE response_history RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE response_history RENAME COLUMN assessment_id TO submission_id')
    op.execute('ALTER TABLE response_history RENAME CONSTRAINT response_history_survey_id_fkey TO response_history_program_id_fkey')
    op.execute('ALTER TABLE response_history RENAME CONSTRAINT response_history_assessment_id_fkey TO response_history_submission_id_fkey')

    op.execute('ALTER INDEX response_assessment_id_measure_id_index RENAME TO response_submission_id_measure_id_index')
    op.execute('ALTER TABLE response RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE response RENAME COLUMN assessment_id TO submission_id')
    op.execute('ALTER TABLE response RENAME CONSTRAINT response_survey_id_fkey TO response_program_id_fkey')
    op.execute('ALTER TABLE response RENAME CONSTRAINT response_assessment_id_fkey TO response_submission_id_fkey')

    op.execute('ALTER INDEX rnode_qnode_id_assessment_id_index RENAME TO rnode_qnode_id_submission_id_index')
    op.execute('ALTER TABLE rnode RENAME COLUMN survey_id TO program_id')
    op.execute('ALTER TABLE rnode RENAME COLUMN assessment_id TO submission_id')
    op.execute('ALTER TABLE rnode RENAME CONSTRAINT rnode_survey_id_fkey TO rnode_program_id_fkey')
    op.execute('ALTER TABLE rnode RENAME CONSTRAINT rnode_assessment_id_fkey TO rnode_submission_id_fkey')


def downgrade():
    op.execute('ALTER TABLE measure RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE measure RENAME CONSTRAINT measure_program_id_fkey TO measure_survey_id_fkey')

    op.execute('ALTER TABLE purchased_survey RENAME COLUMN survey_id TO hierarchy_id')
    op.execute('ALTER TABLE purchased_survey RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE purchased_survey RENAME CONSTRAINT purchased_survey_survey_id_fkey TO purchased_survey_hierarchy_id_fkey')
    op.execute('ALTER TABLE purchased_survey RENAME CONSTRAINT purchased_survey_program_id_fkey TO purchased_survey_survey_id_fkey')

    op.execute('ALTER INDEX qnodemeasure_measure_id_program_id_index RENAME TO qnodemeasure_measure_id_survey_id_index')
    op.execute('ALTER INDEX qnodemeasure_qnode_id_program_id_index RENAME TO qnodemeasure_qnode_id_survey_id_index')
    op.execute('ALTER TABLE qnode_measure_link RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE qnode_measure_link RENAME CONSTRAINT qnode_measure_link_program_id_fkey TO qnode_measure_link_survey_id_fkey')

    op.execute('ALTER INDEX qnode_parent_id_program_id_index RENAME TO qnode_parent_id_survey_id_index')
    op.execute('ALTER INDEX qnode_survey_id_program_id_index RENAME TO qnode_hierarchy_id_survey_id_index')
    op.execute('ALTER TABLE qnode RENAME COLUMN survey_id TO hierarchy_id')
    op.execute('ALTER TABLE qnode RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE qnode RENAME CONSTRAINT qnode_survey_id_fkey TO qnode_hierarchy_id_fkey')
    op.execute('ALTER TABLE qnode RENAME CONSTRAINT qnode_program_id_fkey TO qnode_survey_id_fkey')

    op.execute('ALTER TABLE response_history RENAME COLUMN submission_id TO assessment_id')
    op.execute('ALTER TABLE response_history RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE response_history RENAME CONSTRAINT response_history_submission_id_fkey TO response_history_assessment_id_fkey')
    op.execute('ALTER TABLE response_history RENAME CONSTRAINT response_history_program_id_fkey TO response_history_survey_id_fkey')

    op.execute('ALTER INDEX response_submission_id_measure_id_index RENAME TO response_assessment_id_measure_id_index')
    op.execute('ALTER TABLE response RENAME COLUMN submission_id TO assessment_id')
    op.execute('ALTER TABLE response RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE response RENAME CONSTRAINT response_submission_id_fkey TO response_assessment_id_fkey')
    op.execute('ALTER TABLE response RENAME CONSTRAINT response_program_id_fkey TO response_survey_id_fkey')

    op.execute('ALTER INDEX rnode_qnode_id_submission_id_index RENAME TO rnode_qnode_id_assessment_id_index')
    op.execute('ALTER TABLE rnode RENAME COLUMN submission_id TO assessment_id')
    op.execute('ALTER TABLE rnode RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE rnode RENAME CONSTRAINT rnode_submission_id_fkey TO rnode_assessment_id_fkey')
    op.execute('ALTER TABLE rnode RENAME CONSTRAINT rnode_program_id_fkey TO rnode_survey_id_fkey')

    op.rename_table('submission', 'assessment')
    op.execute('ALTER INDEX submission_pkey RENAME TO assessment_pkey')
    op.execute('ALTER INDEX submission_organisation_id_survey_id_index RENAME TO assessment_organisation_id_hierarchy_id_index')
    op.execute('ALTER TABLE assessment RENAME COLUMN survey_id TO hierarchy_id')
    op.execute('ALTER TABLE assessment RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE assessment RENAME CONSTRAINT submission_approval_check TO assessment_approval_check')
    op.execute('ALTER TABLE assessment RENAME CONSTRAINT submission_organisation_id_fkey TO assessment_organisation_id_fkey')
    op.execute('ALTER TABLE assessment RENAME CONSTRAINT submission_survey_id_fkey TO assessment_hierarchy_id_fkey')
    op.execute('ALTER TABLE assessment RENAME CONSTRAINT submission_program_id_fkey TO assessment_survey_id_fkey')

    op.rename_table('survey', 'hierarchy')
    op.execute('ALTER INDEX survey_pkey RENAME TO hierarchy_pkey')
    op.execute('ALTER TABLE hierarchy RENAME COLUMN program_id TO survey_id')
    op.execute('ALTER TABLE hierarchy RENAME CONSTRAINT survey_program_id_fkey TO hierarchy_survey_id_fkey')

    op.rename_table('program', 'survey')
    op.execute('ALTER INDEX program_pkey RENAME TO survey_pkey')
    op.execute('ALTER INDEX program_created_index RENAME TO survey_created_index')
    op.execute('ALTER INDEX program_tracking_id_index RENAME TO survey_tracking_id_index')
