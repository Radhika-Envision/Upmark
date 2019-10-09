"""add relation ship to organisation and response on Attachment

Revision ID: 47cbc89b3d0
Revises: 3b28546392a
Create Date: 2015-08-26 00:37:12.394378

"""

# revision identifiers, used by Alembic.
revision = '47cbc89b3d0'
down_revision = '3b28546392a'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_foreign_key(
                "fk_attachment_organisation", "attachment",
                "organisation", ["organisation_id"], ["id"])
    op.create_foreign_key(
                "fk_attachment_response", "attachment",
                "response", ["response_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_attachment_organisation", "attachment")
    op.drop_constraint("fk_attachment_response", "attachment")
