"""Activity and subscription tables

Revision ID: 57d1655cd25
Revises: 1140594c2c9
Create Date: 2015-11-11 06:33:40.740567

"""

# revision identifiers, used by Alembic.
revision = '57d1655cd25'
down_revision = '1140594c2c9'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import guid


def upgrade():
    op.create_table('activity',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('subject_id', guid.GUID(), nullable=False),
        sa.Column(
            'verb', sa.Enum(
                'create', 'update', 'state', 'delete', native_enum=False),
            nullable=False),
        sa.Column('object_desc', sa.Text(), nullable=True),
        sa.Column('sticky', sa.Boolean(), nullable=False),
        sa.Column(
            'ob_type', sa.Enum(
                'none',
                'organisation', 'user',
                'program', 'survey', 'qnode', 'measure',
                'submission', native_enum=False),
            nullable=False),
        sa.Column('ob_ids', postgresql.ARRAY(guid.GUID()), nullable=False),
        sa.Column('ob_refs', postgresql.ARRAY(guid.GUID()), nullable=True),
        sa.CheckConstraint(
            'array_length(ob_ids) > 0',
            name='activity_ob_ids_length_constraint'),
        sa.CheckConstraint(
            'array_length(ob_refs) > 0',
            name='activity_ob_refs_length_constraint'),
        sa.ForeignKeyConstraint(['subject_id'], ['appuser.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'activity_created_index', 'activity',
        ['created'],
        unique=False)
    op.create_index(
        'activity_sticky_index', 'activity',
        ['sticky'],
        unique=False,
        postgresql_where=sa.text('activity.sticky = true'))
    op.create_index(
        'activity_subject_id_created_index', 'activity',
        ['subject_id', 'created'],
        unique=False)

    op.create_table('subscription',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('user_id', guid.GUID(), nullable=False),
        sa.Column('subscribed', sa.Boolean(), nullable=False),
        sa.Column(
            'ob_type',
            sa.Enum(
                'none',
                'organisation', 'user',
                'program', 'survey', 'qnode', 'measure',
                'submission', native_enum=False),
            nullable=False),
        sa.Column('ob_refs', postgresql.ARRAY(GUID()), nullable=False),
        sa.CheckConstraint(
            'array_length(ob_refs) > 0',
            name='subscription_ob_refs_length_constraint'),
        sa.ForeignKeyConstraint(['user_id'], ['appuser.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'ob_refs',
            name='subscription_user_ob_refs_unique_constraint')
    )
    op.create_index(
        'subscription_user_id_index', 'subscription',
        ['user_id'],
        unique=False)


def downgrade():
    op.drop_index('subscription_user_id_index', table_name='subscription')
    op.drop_table('subscription')
    op.drop_index('activity_subject_id_created_index', table_name='activity')
    op.drop_index('activity_sticky_index', table_name='activity')
    op.drop_index('activity_created_index', table_name='activity')
    op.drop_table('activity')
