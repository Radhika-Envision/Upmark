"""deleted field for archival

Revision ID: 49c0a4f1e31
Revises: 17d0f7f9190
Create Date: 2015-12-14 12:17:24.231867

"""

# revision identifiers, used by Alembic.
revision = '49c0a4f1e31'
down_revision = '17d0f7f9190'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


appuser = sa.sql.table(
    'appuser',
    sa.Column('enabled', sa.Boolean),
    sa.Column('deleted', sa.DateTime)
)


def upgrade():
    op.add_column('appuser', sa.Column('deleted', sa.DateTime))
    op.execute(appuser.update()
        .where(appuser.c.enabled == False)
        .values({'deleted': sa.func.now()}))
    op.drop_column('appuser', 'enabled')
    op.add_column('assessment', sa.Column('deleted', sa.DateTime))
    op.add_column('hierarchy', sa.Column('deleted', sa.DateTime))
    op.add_column('measure', sa.Column('deleted', sa.DateTime))
    op.add_column('organisation', sa.Column('deleted', sa.DateTime))
    op.add_column('qnode', sa.Column('deleted', sa.DateTime))
    op.add_column('survey', sa.Column('deleted', sa.DateTime))


def downgrade():
    op.drop_column('survey', 'deleted')
    op.drop_column('qnode', 'deleted')
    op.drop_column('organisation', 'deleted')
    op.drop_column('measure', 'deleted')
    op.drop_column('hierarchy', 'deleted')
    op.drop_column('assessment', 'deleted')
    op.add_column('appuser', sa.Column('enabled', sa.Boolean))
    op.execute(appuser.update()
        .values({'enabled': appuser.c.deleted == None}))
    op.drop_column('appuser', 'deleted')
    op.alter_column('appuser', 'enabled', nullable=False)
