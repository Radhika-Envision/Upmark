"""Merge recalc and activity stream

Revision ID: 4bccb877048
Revises: a4df794479, 37e7e2791e9
Create Date: 2015-12-02 04:18:02.852589

"""

# revision identifiers, used by Alembic.
revision = '4bccb877048'
down_revision = ('a4df794479', '37e7e2791e9')
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    pass


def downgrade():
    pass
