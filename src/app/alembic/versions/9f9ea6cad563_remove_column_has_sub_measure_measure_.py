"""remove_column_has_sub_measure_measure_table

Revision ID: 9f9ea6cad563
Revises: 009beb9045c3
Create Date: 2019-10-09 11:31:32.424611

"""

# revision identifiers, used by Alembic.
revision = '9f9ea6cad563'
down_revision = '009beb9045c3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('measure', 'has_sub_measures')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('measure', sa.Column('has_sub_measures', sa.BOOLEAN(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###