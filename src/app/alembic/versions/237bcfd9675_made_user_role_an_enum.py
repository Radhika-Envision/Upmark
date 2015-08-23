"""Made user role an enum

Revision ID: 237bcfd9675
Revises: 4d5c9a3ae7f
Create Date: 2015-08-23 13:21:14.331148

"""

# revision identifiers, used by Alembic.
revision = '237bcfd9675'
down_revision = '4d5c9a3ae7f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    roles = ['admin', 'author', 'authority', 'consultant', 'org_admin', 'clerk']
    options = ", ".join("'%s'::character varying" % r for r in roles)
    op.create_check_constraint('appuser_role_check', 'appuser',
        "role::text = ANY (ARRAY[%s]::text[])" % options)


def downgrade():
    op.drop_constraint('appuser_role_check', 'appuser', type_='check')

