"""Moved response type to own table

Revision ID: 151aa56ffd8
Revises: 1ef306add5e
Create Date: 2016-08-22 03:57:41.057928

"""

# revision identifiers, used by Alembic.
revision = '151aa56ffd8'
down_revision = '1ef306add5e'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('response_type',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('program_id', guid.GUID(), nullable=False),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('parts', postgresql.JSON(), nullable=False),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['program_id'], ['program.id'], ),
        sa.PrimaryKeyConstraint('id', 'program_id')
    )
    op.add_column('measure', sa.Column('response_type_id', guid.GUID()))

    # TODO: migrate data

    op.create_foreign_key('measure_response_type_id_fkey',
        'measure', 'response_type',
        ['response_type_id', 'program_id'],
        ['id', 'program_id'])
    op.alter_column('measure', 'response_type_id', nullable=False)
    op.drop_column('measure', 'response_type')
    op.drop_column('program', 'response_types')


def downgrade():
    op.add_column('program', sa.Column('response_types', postgresql.JSON()))
    op.add_column('measure', sa.Column('response_type', sa.TEXT()))

    # TODO: migrate data

    op.alter_column('program', 'response_types', nullable=False)
    op.alter_column('measure', 'response_type', nullable=False)

    op.drop_constraint('measure_response_type_id_fkey', 'measure', type_='foreignkey')
    op.drop_column('measure', 'response_type_id')
    op.drop_table('response_type')
