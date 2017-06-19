"""Added custom query tables

Revision ID: 76620faac78d
Revises: f49cdcc1b233
Create Date: 2017-06-09 09:09:47.658271

"""

# revision identifiers, used by Alembic.
revision = '76620faac78d'
down_revision = 'f49cdcc1b233'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy import column, func
from sqlalchemy.dialects.postgresql import array, TEXT
from sqlalchemy.sql.expression import cast

import guid


def upgrade():
    op.create_table('custom_query_history',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('modified', sa.DateTime(), nullable=False),
        sa.Column('user_id', guid.GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('changed', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['appuser.id'], ),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.create_table('custom_query',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('modified', sa.DateTime(), nullable=False),
        sa.Column('user_id', guid.GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['appuser.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    ob_types = array([
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        'custom_query'], type_=TEXT)
    op.drop_constraint('activity_ob_type_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.drop_constraint('subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))

    op.drop_constraint('activity_verbs_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_verbs_check', 'activity',
        """verbs <@ ARRAY[
            'broadcast',
            'create', 'update', 'state', 'delete', 'undelete',
            'relation', 'reorder_children',
            'report'
        ]::varchar[]""")


def downgrade():
    op.execute('''
        DELETE FROM activity AS a
        WHERE ARRAY['report']::varchar[] <@ a.verbs''')

    op.execute('''
        DELETE FROM activity AS a
        WHERE 'custom_query' = a.ob_type''')
    op.execute('''
        DELETE FROM subscription AS s
        WHERE 'custom_query' = s.ob_type''')

    op.drop_constraint('activity_verbs_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_verbs_check', 'activity',
        """verbs <@ ARRAY[
            'broadcast',
            'create', 'update', 'state', 'delete', 'undelete',
            'relation', 'reorder_children'
        ]::varchar[]""")

    ob_types = array([
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response'], type_=TEXT)
    op.drop_constraint('activity_ob_type_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.drop_constraint('subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))

    op.drop_table('custom_query')
    op.drop_table('custom_query_history')
