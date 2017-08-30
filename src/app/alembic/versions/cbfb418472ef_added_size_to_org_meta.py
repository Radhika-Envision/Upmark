"""added size to org meta

Revision ID: cbfb418472ef
Revises: d7124663cebc
Create Date: 2017-08-30 01:17:41.103886

"""

# revision identifiers, used by Alembic.
revision = 'cbfb418472ef'
down_revision = 'd7124663cebc'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('org_meta', sa.Column('size', sa.Enum('small', 'medium', 'large', native_enum=False), nullable=True))


def downgrade():
    op.drop_column('org_meta', 'size')
