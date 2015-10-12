"""add reference on response history

Revision ID: 31e60f5e005
Revises: 1dbcbe2a1a6
Create Date: 2015-10-12 01:01:29.128495

"""

# revision identifiers, used by Alembic.
revision = '31e60f5e005'
down_revision = '1dbcbe2a1a6'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    op.create_foreign_key(
        'fk_response_history_user',
        'response_history', 'appuser',
        ['user_id'], ['id'],
    )


def downgrade():
    op.drop_constraint(
        'fk_response_history_user',
        'response_history'
    )
