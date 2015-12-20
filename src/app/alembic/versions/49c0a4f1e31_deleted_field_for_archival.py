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
    sa.Column('deleted', sa.Boolean)
)

other_tables = ['assessment', 'hierarchy', 'measure', 'organisation', 'qnode',
                'survey']


def upgrade():
    op.execute(
        "REVOKE SELECT"
        " ON appuser FROM analyst")

    op.add_column('appuser', sa.Column('deleted', sa.Boolean))
    op.execute(appuser.update()
        .values({'deleted': appuser.c.enabled == False}))
    op.drop_column('appuser', 'enabled')

    for t in other_tables:
        table = sa.sql.table(t, sa.Column('deleted', sa.Boolean))
        op.add_column(t, sa.Column('deleted', sa.Boolean))
        op.execute(table.update().values({'deleted': False}))
        op.alter_column(t, 'deleted', nullable=False)

    op.execute(
        "GRANT SELECT"
        " (id, organisation_id, email, name, role, created, deleted)"
        " ON appuser TO analyst")


def downgrade():
    op.execute(
        "REVOKE SELECT"
        " ON appuser FROM analyst")

    for t in other_tables:
        op.drop_column(t, 'deleted')

    op.add_column('appuser', sa.Column('enabled', sa.Boolean))
    op.execute(appuser.update()
        .values({'enabled': appuser.c.deleted == False}))
    op.drop_column('appuser', 'deleted')
    op.alter_column('appuser', 'enabled', nullable=False)

    op.execute(
        "GRANT SELECT"
        " (id, organisation_id, email, name, role, created, enabled)"
        " ON appuser TO analyst")
