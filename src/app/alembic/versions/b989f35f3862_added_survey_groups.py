"""Added survey groups

Revision ID: b989f35f3862
Revises: 76620faac78d
Create Date: 2017-07-19 07:08:51.696011

"""

# revision identifiers, used by Alembic.
revision = 'b989f35f3862'
down_revision = '76620faac78d'
branch_labels = None
depends_on = None

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import column, func
from sqlalchemy.dialects.postgresql import array, TEXT
from sqlalchemy.sql.expression import cast

import deps_b989f35f3862 as model


def upgrade():
    survey_group_table = op.create_table(
        'survey_group',
        sa.Column('id', model.guid.GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    ob_types = array([
        'group',
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        'custom_query'], type_=TEXT)
    op.drop_constraint(
        'activity_ob_type_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.drop_constraint(
        'subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))

    roles = array([
        'super_admin', 'admin', 'author', 'authority', 'consultant',
        'org_admin', 'clerk'])
    op.drop_constraint('appuser_role_check', 'appuser', type_='check')
    op.create_check_constraint(
        'appuser_role_check', 'appuser',
        cast(column('role'), TEXT) == func.any(roles))

    op.bulk_insert(survey_group_table, [
        {
            'id': model.guid.GUID.gen(),
            'title': "DEFAULT SURVEY GROUP",
            'created': datetime.datetime.now(),
            'deleted': False,
        },
    ])


def downgrade():
    op.drop_table('survey_group')
    op.execute('''
        DELETE FROM activity
        WHERE ob_type = 'group'
    ''')
    op.execute('''
        DELETE FROM subscription
        WHERE ob_type = 'group'
    ''')

    ob_types = array([
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        'custom_query'], type_=TEXT)
    op.drop_constraint(
        'activity_ob_type_check', 'activity', type_='check')
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.drop_constraint(
        'subscription_ob_type_check', 'subscription', type_='check')
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))

    roles = array([
        'admin', 'author', 'authority', 'consultant', 'org_admin', 'clerk'])
    op.execute("""
        UPDATE appuser
        SET role = 'admin'
        WHERE role = 'super_admin'
    """)
    op.drop_constraint('appuser_role_check', 'appuser', type_='check')
    op.create_check_constraint(
        'appuser_role_check', 'appuser',
        cast(column('role'), TEXT) == func.any(roles))
