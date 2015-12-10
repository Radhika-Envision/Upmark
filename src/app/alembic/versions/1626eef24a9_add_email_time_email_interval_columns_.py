"""add email_time, email_interval columns to appUser

Revision ID: 1626eef24a9
Revises: 12e2c8b78e6
Create Date: 2015-12-03 03:19:17.637591

"""

# revision identifiers, used by Alembic.
revision = '1626eef24a9'
down_revision = '12e2c8b78e6'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


ONE_DAY_S = 60 * 60 * 24

appuser = table('appuser', column('email_interval', sa.Integer))


def upgrade():
    op.add_column('appuser', sa.Column('email_time', sa.DateTime(), nullable=True))
    op.add_column('appuser', sa.Column('email_interval', sa.Integer(), nullable=True))
    op.execute(
        appuser.update()
            .values({'email_interval': op.inline_literal(ONE_DAY_S)})
    )
    op.alter_column('appuser', 'email_interval', nullable=False)


def downgrade():
    op.drop_column('appuser', 'email_interval')
    op.drop_column('appuser', 'email_time')
