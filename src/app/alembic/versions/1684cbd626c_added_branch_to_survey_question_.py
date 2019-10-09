"""Survey question branch field

Revision ID: 1684cbd626c
Revises: 159de9597b2
Create Date: 2015-07-01 05:24:25.635465

"""

# revision identifiers, used by Alembic.
revision = '1684cbd626c'
down_revision = '159de9597b2'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


table_names = [
    'survey', 'function', 'process', 'subprocess', 'measure',
]
for table_name in table_names[:]:
    table_names.append(table_name + '_history')

table_names += ['measureset', 'measureset_measure_link']

tables = {
    table_name: sa.sql.table(table_name,
        sa.sql.column('branch', sa.Text)
    ) for table_name in table_names
}


def upgrade():
    for name, table in tables.items():
        op.add_column(name, sa.Column('branch', sa.Text(), nullable=True))
        op.execute(table.update().values({'branch': 'no branch'}))
        op.alter_column(name, 'branch', nullable=False)


def downgrade():
    for name in table_names:
        op.drop_column(name, 'branch')
