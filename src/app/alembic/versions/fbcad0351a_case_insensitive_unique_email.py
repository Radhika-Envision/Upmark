"""Case insensitive unique email

Revision ID: fbcad0351a
Revises: 159de9597b2
Create Date: 2015-06-24 04:54:47.744219

"""

# revision identifiers, used by Alembic.
revision = 'fbcad0351a'
down_revision = '159de9597b2'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.drop_constraint('organisation_name_key', 'organisation')
    op.drop_constraint('appuser_email_key', 'appuser')
    op.create_index(
        'organisation_name_key', 'organisation', [sa.text('lower(name)')],
        unique=True)
    op.create_index(
        'appuser_email_key', 'appuser', [sa.text('lower(email)')],
        unique=True)


def downgrade():
    op.drop_index('organisation_name_key', 'organisation')
    op.drop_index('appuser_email_key', 'appuser')
    op.create_unique_constraint(
        'organisation_name_key', 'organisation', ['name'])
    op.create_unique_constraint(
        'appuser_email_key', 'appuser', ['email'])
