"""System config generalisation

Revision ID: 4959ae79bed
Revises: 94a189659
Create Date: 2016-08-05 01:02:34.605964

"""

# revision identifiers, used by Alembic.
revision = '4959ae79bed'
down_revision = '94a189659'
branch_labels = None
depends_on = None

from datetime import datetime
import inspect
import json
import os

from alembic import op
import sqlalchemy as sa


systemconfig = sa.sql.table(
    'systemconfig',
    sa.sql.column('name', sa.String),
    sa.sql.column('human_name', sa.String),
    sa.sql.column('description', sa.String),
    sa.sql.column('user_defined', sa.Boolean),
    sa.sql.column('modified', sa.DateTime),
)


def upgrade():
    op.add_column('systemconfig', sa.Column('data', sa.LargeBinary()))
    op.add_column('systemconfig', sa.Column('modified', sa.DateTime()))

    op.drop_column('systemconfig', 'description')
    op.drop_column('systemconfig', 'human_name')
    op.drop_column('systemconfig', 'user_defined')

    # Rename private data, following Python's convention for marking fields as
    # private.
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == 'cookie_secret')
        .values({'name': '_cookie_secret'}))
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == 'analyst_password')
        .values({'name': '_analyst_password'}))
    op.execute(systemconfig.update()
        .values({
            'modified': datetime.utcnow(),
        }))

    op.alter_column('systemconfig', 'modified', nullable=False)


def downgrade():
    op.add_column('systemconfig', sa.Column('user_defined', sa.Boolean))
    op.add_column('systemconfig', sa.Column('human_name', sa.String))
    op.add_column('systemconfig', sa.Column('description', sa.String))

    op.execute(systemconfig.update()
        .values({
            'human_name': systemconfig.c.name,
            'description': systemconfig.c.name,
        }))
    op.execute(systemconfig.update()
        .where(systemconfig.c.name.like(r'_%'))
        .values({
            'user_defined': False,
        }))
    op.execute(systemconfig.update()
        .where(systemconfig.c.user_defined == None)
        .values({
            'user_defined': True,
        }))

    op.execute(systemconfig.update()
        .where(systemconfig.c.name == '_analyst_password')
        .values({'name': 'analyst_password'}))
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == '_cookie_secret')
        .values({'name': 'cookie_secret'}))

    op.alter_column('systemconfig', 'user_defined', nullable=False)
    op.alter_column('systemconfig', 'user_defined', nullable=False)
    op.alter_column('systemconfig', 'user_defined', nullable=False)

    op.drop_column('systemconfig', 'modified')
    op.drop_column('systemconfig', 'data')
