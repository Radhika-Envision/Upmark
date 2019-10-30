"""add_column_submeasure_id_attachment_table

Revision ID: 9663878a207b
Revises: 009beb9045c3
Create Date: 2019-10-09 11:38:45.702877

"""

# revision identifiers, used by Alembic.
revision = '9663878a207b'
down_revision = '009beb9045c3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import old_deps.guid as guid
def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    #op.drop_table('measure_measure')
    op.add_column('attachment', sa.Column('submeasure_id', guid.GUID(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('attachment', 'submeasure_id')
    #op.create_table('measure_measure',
    #sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
    #sa.Column('measure_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #sa.Column('program_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #sa.Column('parent_measure_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #sa.Column('parent_program_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #sa.ForeignKeyConstraint(['measure_id', 'program_id'], ['measure.id', 'measure.program_id'], name='measure_measure_measure_id_fkey'),
    #sa.ForeignKeyConstraint(['parent_measure_id', 'parent_program_id'], ['measure.id', 'measure.program_id'], name='measure_measure_parent_measure_id_fkey'),
    #sa.PrimaryKeyConstraint('id', name='measure_measure_pkey')
    #)
    # ### end Alembic commands ###