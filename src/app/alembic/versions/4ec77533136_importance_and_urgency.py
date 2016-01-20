"""Importance and urgency

Revision ID: 4ec77533136
Revises: 1626eef24a9
Create Date: 2016-01-20 09:11:15.910327

"""

# revision identifiers, used by Alembic.
revision = '4ec77533136'
down_revision = '1626eef24a9'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('appuser', 'deleted',
               existing_type=sa.BOOLEAN(),
               nullable=False)

    op.add_column('rnode', sa.Column('importance', sa.Float(), nullable=True))
    op.add_column('rnode', sa.Column('urgency', sa.Float(), nullable=True))
    op.add_column('rnode', sa.Column('max_importance', sa.Float(), nullable=True))
    op.add_column('rnode', sa.Column('max_urgency', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('rnode', 'max_urgency')
    op.drop_column('rnode', 'max_importance')
    op.drop_column('rnode', 'urgency')
    op.drop_column('rnode', 'importance')

    op.alter_column('appuser', 'deleted',
               existing_type=sa.BOOLEAN(),
               nullable=True)
