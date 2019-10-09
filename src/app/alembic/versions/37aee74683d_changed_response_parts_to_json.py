"""Changed response_parts to JSON

Revision ID: 37aee74683d
Revises: 3382ad148a1
Create Date: 2015-08-24 10:33:37.722372

"""

# revision identifiers, used by Alembic.
revision = '37aee74683d'
down_revision = '3382ad148a1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


def upgrade():
    op.execute('ALTER TABLE response ALTER COLUMN response_parts TYPE JSON USING response_parts::JSON')
    op.execute('ALTER TABLE response_history ALTER COLUMN response_parts TYPE JSON USING response_parts::JSON')


def downgrade():
    # Technically, the database already used JSON for this field when created
    # fresh - but the change was never added to Alembic, so for consistency
    # assume the downgrade should be to Text.
    op.execute('ALTER TABLE response ALTER COLUMN response_parts TYPE TEXT USING response_parts::TEXT')
    op.execute('ALTER TABLE response_history ALTER COLUMN response_parts TYPE TEXT USING response_parts::TEXT')
