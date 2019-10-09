"""add_analyst_permission_for_response_type

Revision ID: 009beb9045c3
Revises: a8ae1a2e2b16
Create Date: 2018-01-16 02:43:17.287219

"""

# revision identifiers, used by Alembic.
revision = '009beb9045c3'
down_revision = 'a8ae1a2e2b16'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("GRANT SELECT ON response_type TO analyst")

def downgrade():
    op.execute("REVOKE SELECT ON response_type FROM analyst")
