"""Added parameterisation flag to CustomQuery

Revision ID: 13212743e348
Revises: 009beb9045c3
Create Date: 2018-01-24 07:12:40.037579

"""

# revision identifiers, used by Alembic.
revision = '13212743e348'
down_revision = '009beb9045c3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('custom_query',
        sa.Column('is_parameterised', sa.Boolean(), nullable=True))
    op.execute("""UPDATE custom_query SET is_parameterised = 'f'""")
    op.alter_column('custom_query', 'is_parameterised', nullable=False)

    op.add_column('custom_query_history',
        sa.Column('is_parameterised', sa.Boolean(), nullable=True))
    op.execute("""UPDATE custom_query_history SET is_parameterised = 'f'""")
    op.alter_column('custom_query_history', 'is_parameterised', nullable=False)

def downgrade():
    op.drop_column('custom_query_history', 'is_parameterised')
    op.drop_column('custom_query', 'is_parameterised')
