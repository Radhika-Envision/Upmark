"""add submeasure id in attachment and group in qnode and measureid seq link in measure

Revision ID: d6ebaa606356
Revises: 0e0b20b46cd0
Create Date: 2019-12-20 15:51:02.448514

"""

# revision identifiers, used by Alembic.
revision = 'd6ebaa606356'
down_revision = '0e0b20b46cd0'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
import old_deps.guid as guid

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('attachment', sa.Column('submeasure_id', guid.GUID(), nullable=True))
    op.add_column('measure', sa.Column('measure_id', guid.GUID(), nullable=True))
    op.add_column('measure', sa.Column('submeasure_seq', sa.Integer(), nullable=True))
    op.add_column('qnode', sa.Column('group', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('qnode', 'group')
    op.drop_column('measure', 'submeasure_seq')
    op.drop_column('measure', 'measure_id')
    op.drop_column('attachment', 'submeasure_id')
    # ### end Alembic commands ###