"""added logo to survey groups

Revision ID: d7124663cebc
Revises: b989f35f3862
Create Date: 2017-08-16 05:03:15.164800

"""

# revision identifiers, used by Alembic.
revision = 'd7124663cebc'
down_revision = 'b989f35f3862'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('surveygroup', sa.Column('logo', sa.LargeBinary()))


def downgrade():
    op.drop_column('surveygroup', 'logo')
