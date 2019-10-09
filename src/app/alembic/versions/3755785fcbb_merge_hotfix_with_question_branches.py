"""Merge hotfix with question branches

Revision ID: 3755785fcbb
Revises: 1684cbd626c, fbcad0351a
Create Date: 2015-07-05 11:29:02.853980

"""

# revision identifiers, used by Alembic.
revision = '3755785fcbb'
down_revision = ('1684cbd626c', 'fbcad0351a')
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Nothing required: no merge conflicts.
    pass


def downgrade():
    # Nothing required: no merge conflicts.
    pass
