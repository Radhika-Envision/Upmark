"""Added analyst user

Revision ID: 50058a07f33
Revises: 31e60f5e005
Create Date: 2015-10-15 10:31:41.498561

"""

# revision identifiers, used by Alembic.
revision = '50058a07f33'
down_revision = '31e60f5e005'
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
    password = base64.b32encode(os.urandom(30)).decode('ascii')

    op.execute(
        "INSERT INTO systemconfig"
        " (name, human_name, user_defined, value, description)"
        " VALUES('{}', '{}', {}, '{}', '{}')".format(
            'analyst_password', 
            "Analyst password",
            False,
            password,
            "Password for read-only database access"))

    op.execute("CREATE USER analyst WITH PASSWORD '{}'".format(password))
    op.execute("GRANT USAGE ON SCHEMA public TO analyst")
    op.execute("GRANT SELECT"
            " (id, organisation_id, email, name, role, created, enabled)"
            " ON appuser TO analyst")
    for table in table_names:
        op.execute("GRANT SELECT ON {} TO analyst".format(table))


def downgrade():
    op.execute("REVOKE SELECT"
            " (id, organisation_id, email, name, role, created, enabled)"
            " ON appuser FROM analyst")

    for table in table_names:
        op.execute("REVOKE SELECT ON {} FROM analyst".format(table))
    op.execute("REVOKE USAGE ON SCHEMA public FROM analyst")
    op.execute("DROP ROLE analyst")
    op.execute("DELETE FROM systemconfig WHERE name = 'analyst_password'")
