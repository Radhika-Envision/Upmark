"""Added more file_name field and change id types to GUID and not nullable

Revision ID: 3b28546392a
Revises: 37aee74683d
Create Date: 2015-08-25 00:48:18.457824

"""

# revision identifiers, used by Alembic.
revision = '3b28546392a'
down_revision = '37aee74683d'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
import old_deps.guid as guid

def upgrade():
    op.add_column('attachment', sa.Column('file_name', sa.Text(), nullable=True))
    op.execute("ALTER TABLE attachment ALTER COLUMN response_id TYPE UUID USING response_id::UUID")
    op.execute("ALTER TABLE attachment ALTER COLUMN response_id SET NOT NULL")
    op.execute("ALTER TABLE attachment ALTER COLUMN organisation_id TYPE UUID USING organisation_id::UUID")
    op.execute("ALTER TABLE attachment ALTER COLUMN organisation_id SET NOT NULL")


def downgrade():
    op.execute("ALTER TABLE attachment ALTER COLUMN response_id TYPE TEXT USING response_id::TEXT")
    op.execute("ALTER TABLE attachment ALTER COLUMN response_id SET NOT NULL")
    op.execute("ALTER TABLE attachment ALTER COLUMN organisation_id TYPE TEXT USING organisation_id::TEXT")
    op.execute("ALTER TABLE attachment ALTER COLUMN organisation_id SET NOT NULL")
    op.drop_column('attachment', 'file_name')
