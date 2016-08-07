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

import inspect
import json
import os

from alembic import op
import sqlalchemy as sa


systemconfig = sa.sql.table(
    'systemconfig',
    sa.sql.column('name', sa.String)
)


def upgrade():
    op.add_column('systemconfig', sa.Column('data', sa.LargeBinary(), nullable=True))
    op.add_column('systemconfig', sa.Column('mime_type', sa.String(), nullable=True))

    op.drop_column('systemconfig', 'description')
    op.drop_column('systemconfig', 'human_name')
    op.drop_column('systemconfig', 'user_defined')

    op.execute(systemconfig.update()
        .where(systemconfig.c.name == 'cookie_secret')
        .values({'name': '_cookie_secret'}))
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == 'analyst_password')
        .values({'name': '_analyst_password'}))


def downgrade():
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == '_analyst_password')
        .values({'name': 'analyst_password'}))
    op.execute(systemconfig.update()
        .where(systemconfig.c.name == '_cookie_secret')
        .values({'name': 'cookie_secret'}))

    op.add_column('systemconfig', sa.Column('user_defined', sa.Boolean))
    op.add_column('systemconfig', sa.Column('human_name', sa.String))
    op.add_column('systemconfig', sa.Column('description', sa.String))
    populate_defaults()
    op.alter_column('systemconfig', 'user_defined', nullable=False)
    op.alter_column('systemconfig', 'user_defined', nullable=False)
    op.alter_column('systemconfig', 'user_defined', nullable=False)

    op.drop_column('systemconfig', 'mime_type')
    op.drop_column('systemconfig', 'data')


def populate_defaults():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    package_dir = os.path.dirname(frameinfo.filename)
    conf_file = os.path.join('..', '..', '..', 'sysconfg_schema.yaml')
    schema = json.loads(conf_file)
    for s in schema:
        op.execute(systemconfig.update()
            .where(systemconfig.c.name == s['name'])
            .values({
                'human_name': s['human_name'],
                'description': s['description'],
                'user_defined': True,
            }))

    op.execute(systemconfig.update()
        .where(systemconfig.c.user_defined == None)
        .values({'user_defined': False}))
    op.execute(systemconfig.update()
        .where(systemconfig.c.human_name == None)
        .values({'human_name': systemconfig.c.name}))
