"""User disable

Revision ID: 159de9597b2
Revises: 456efed92cd
Create Date: 2015-06-24 00:26:47.665774

"""

# revision identifiers, used by Alembic.
revision = '159de9597b2'
down_revision = '456efed92cd'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


appuser = sa.sql.table('appuser',
    sa.sql.column('enabled', sa.Boolean)
)
appuser_history = sa.sql.table('appuser_history',
    sa.sql.column('enabled', sa.Boolean)
)


def upgrade():
    op.add_column('appuser', sa.Column('enabled', sa.Boolean(), nullable=True))
    op.add_column('appuser_history', sa.Column('enabled', sa.Boolean(), nullable=True))
    op.execute(appuser.update().values({'enabled': True}))
    op.execute(appuser_history.update().values({'enabled': True}))
    op.alter_column('appuser', 'enabled', nullable=False)
    op.alter_column('appuser_history', 'enabled', nullable=False)


def downgrade():
    op.drop_column('appuser_history', 'enabled')
    op.drop_column('appuser', 'enabled')
