"""add submeasure id in attachment and group in qnode

Revision ID: 91aa4a91a5f9
Revises: 009beb9045c3
Create Date: 2019-12-05 12:43:47.373370

"""

# revision identifiers, used by Alembic.
revision = '91aa4a91a5f9'
down_revision = '009beb9045c3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

import old_deps.guid as guid

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('attachment', sa.Column('submeasure_id', guid.GUID(), nullable=True))
    op.add_column('qnode', sa.Column('group', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('qnode', 'group')
    op.drop_column('attachment', 'submeasure_id')
    # ### end Alembic commands ###