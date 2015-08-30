"""add storage field on attachment

Revision ID: 3faa8e4675f
Revises: 3d04b267d64
Create Date: 2015-08-27 06:44:31.686973

"""

# revision identifiers, used by Alembic.
revision = '3faa8e4675f'
down_revision = '3d04b267d64'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


def upgrade():
    op.add_column('attachment', sa.Column(
        'storage', sa.Enum('external', 'aws', 'database', native_enum=False)))

    attachment = table(
        'attachment', column('storage'), column('url'), column('file_name'))

    op.execute(attachment.update().where(attachment.c.url!=None)\
        .values(storage='external'))
    op.execute(attachment.update().where(attachment.c.url==None)\
        .values(storage='database'))

    op.alter_column('attachment', 'storage', nullable=False)


def downgrade():
    op.drop_column('attachment', 'storage')
