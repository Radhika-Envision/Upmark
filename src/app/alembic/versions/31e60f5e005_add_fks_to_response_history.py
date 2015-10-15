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

import os
import base64

from alembic import op

table_names = ["assessment", "attachment", "hierarchy", 
    "measure", "organisation", "purchased_survey", 
    "qnode", "qnode_measure_link", "response", 
    "response_history", "rnode", "survey"]

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

    password = base64.b64encode(os.urandom(50)).decode('ascii')

    op.execute("INSERT INTO systemconfig VALUES('{}', '{}', {}, '{}', '{}')"
        .format(
        'analyst_password', 
        "Analyst password",
        False,
        password,
        "Password for read-only database access"))

    op.execute("CREATE USER analyst WITH PASSWORD '{}'".format(password))
    op.execute("GRANT SELECT"
            " (id, organisation_id, email, name, role, created, enabled)"
            " ON appuser TO analyst")
    for table in table_names:
        op.execute("GRANT SELECT ON {} TO analyst".format(table))


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

    op.execute("REVOKE SELECT"
            " (id, organisation_id, email, name, role, created, enabled)"
            " ON appuser FROM analyst")

    for table in table_names:
        op.execute("REVOKE SELECT ON {} FROM analyst".format(table))
    op.execute("DROP ROLE analyst")
    op.execute("DELETE FROM systemconfig WHERE name = 'analyst_password'")
