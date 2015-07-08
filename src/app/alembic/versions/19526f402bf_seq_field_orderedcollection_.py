"""seq field orderedcollection compatibility

Revision ID: 19526f402bf
Revises: 25984b9bdb8
Create Date: 2015-07-08 23:38:47.740574

"""

# revision identifiers, used by Alembic.
revision = '19526f402bf'
down_revision = '25984b9bdb8'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.alter_column('function', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('function_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('measure', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('measure_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('process', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('process_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('subprocess', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('subprocess_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade():
    op.alter_column('subprocess_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('subprocess', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('process_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('process', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('measure_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('measure', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('function_history', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('function', 'seq',
               existing_type=sa.INTEGER(),
               nullable=False)
