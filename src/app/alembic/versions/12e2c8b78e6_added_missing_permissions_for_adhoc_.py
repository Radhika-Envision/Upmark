"""Added missing permissions for adhoc query

Revision ID: 12e2c8b78e6
Revises: 49c0a4f1e31
Create Date: 2015-12-20 11:20:28.345728

"""

# revision identifiers, used by Alembic.
revision = '12e2c8b78e6'
down_revision = '49c0a4f1e31'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("GRANT SELECT ON activity TO analyst")
    op.execute("GRANT SELECT ON subscription TO analyst")


def downgrade():
    op.execute("REVOKE SELECT ON activity FROM analyst")
    op.execute("REVOKE SELECT ON subscription FROM analyst")
