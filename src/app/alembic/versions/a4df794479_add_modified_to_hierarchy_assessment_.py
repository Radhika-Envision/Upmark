"""add modified to Hierarchy, Assessment for recalculating

Revision ID: a4df794479
Revises: 1140594c2c9
Create Date: 2015-11-26 02:12:59.548802

"""

# revision identifiers, used by Alembic.
revision = 'a4df794479'
down_revision = '1140594c2c9'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('assessment', sa.Column('modified', sa.DateTime(), nullable=True))
    op.add_column('hierarchy', sa.Column('modified', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('hierarchy', 'modified')
    op.drop_column('assessment', 'modified')
