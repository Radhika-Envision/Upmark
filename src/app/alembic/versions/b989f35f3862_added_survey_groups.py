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
from sqlalchemy import column, ForeignKey, func
from sqlalchemy.dialects.postgresql import array, TEXT
from sqlalchemy.sql.expression import cast

from deps_b989f35f3862.guid import GUID


def upgrade():
    survey_group_table = op.create_table(
        'surveygroup',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'surveygroup_title_key',
        'surveygroup',
        ['title'], unique=False)

    op.create_table(
        'organisation_surveygroup',
        sa.Column('organisation_id', GUID, ForeignKey('organisation.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id'))
    )

    op.create_table(
        'user_surveygroup',
        sa.Column('user_id', GUID, ForeignKey('appuser.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id'))
    )

    op.create_table(
        'program_surveygroup',
        sa.Column('program_id', GUID, ForeignKey('program.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id'))
    )

    ob_types = array([
        'surveygroup',
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

    group_id = GUID.gen()
    op.bulk_insert(survey_group_table, [
        {
            'id': group_id,
            'title': "DEFAULT SURVEY GROUP",
            'created': datetime.datetime.now(),
            'deleted': False,
        },
    ])
    op.execute("""
        INSERT INTO organisation_surveygroup
        (organisation_id, surveygroup_id)
        SELECT o.id, '%s'
        FROM organisation AS o
    """ % group_id)
    op.execute("""
        INSERT INTO user_surveygroup
        (user_id, surveygroup_id)
        SELECT u.id, '%s'
        FROM appuser AS u
    """ % group_id)
    op.execute("""
        INSERT INTO program_surveygroup
        (program_id, surveygroup_id)
        SELECT p.id, '%s'
        FROM program AS p
    """ % group_id)


def downgrade():
    op.drop_table('program_surveygroup')
    op.drop_table('user_surveygroup')
    op.drop_table('organisation_surveygroup')
    op.drop_table('surveygroup')

    op.execute('''
        DELETE FROM activity
        WHERE ob_type = 'surveygroup'
    ''')
    op.execute('''
        DELETE FROM subscription
        WHERE ob_type = 'surveygroup'
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
