"""Changed created date to datetime

Revision ID: 2c77b7a9033
Revises: 3755785fcbb
Create Date: 2015-07-08 00:49:21.359028

"""

# revision identifiers, used by Alembic.
revision = '2c77b7a9033'
down_revision = '3755785fcbb'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


table_names = [
    'organisation', 'appuser', 'survey', 'assessment',
]
for table_name in table_names[:]:
    table_names.append(table_name + '_history')


def upgrade():
    for name in table_names:
        op.alter_column(name, 'created', type_=sa.DateTime)


def downgrade():
    for name in table_names:
        op.alter_column(name, 'created', type_=sa.Date)
