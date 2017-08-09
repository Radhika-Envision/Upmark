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
from sqlalchemy import column, ForeignKey, func, Index
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
        ['title'], unique=True)

    op.create_table(
        'organisation_surveygroup',
        sa.Column('organisation_id', GUID, ForeignKey('organisation.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id')),
        Index(
            'organisation_surveygroup_organisation_id_index',
            'organisation_id'),
        Index(
            'organisation_surveygroup_surveygroup_id_index',
            'surveygroup_id'),
    )

    op.create_table(
        'user_surveygroup',
        sa.Column('user_id', GUID, ForeignKey('appuser.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id')),
        Index('user_surveygroup_organisation_id_index', 'user_id'),
        Index('user_surveygroup_surveygroup_id_index', 'surveygroup_id'),
    )

    op.create_table(
        'program_surveygroup',
        sa.Column('program_id', GUID, ForeignKey('program.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id')),
        Index('program_surveygroup_program_id_index', 'program_id'),
        Index('program_surveygroup_surveygroup_id_index', 'surveygroup_id'),
    )

    op.create_table(
        'activity_surveygroup',
        sa.Column('activity_id', GUID, ForeignKey('activity.id')),
        sa.Column('surveygroup_id', GUID, ForeignKey('surveygroup.id')),
        Index('activity_surveygroup_activity_id_index', 'activity_id'),
        Index('activity_surveygroup_surveygroup_id_index', 'surveygroup_id'),
    )

    op.create_table(
        'id_map',
        sa.Column('old_id', GUID, nullable=False, primary_key=True),
        sa.Column('new_id', GUID, nullable=False),
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
        SELECT organisation.id, '%s'
        FROM organisation
    """ % group_id)
    op.execute("""
        INSERT INTO user_surveygroup
        (user_id, surveygroup_id)
        SELECT appuser.id, '%s'
        FROM appuser
    """ % group_id)
    op.execute("""
        INSERT INTO program_surveygroup
        (program_id, surveygroup_id)
        SELECT program.id, '%s'
        FROM program
    """ % group_id)
    op.execute("""
        INSERT INTO activity_surveygroup
        (activity_id, surveygroup_id)
        SELECT activity.id, '%s'
        FROM activity
    """ % group_id)

    op.execute("GRANT SELECT ON organisation_surveygroup TO analyst")
    op.execute("GRANT SELECT ON activity_surveygroup TO analyst")
    op.execute("GRANT SELECT ON user_surveygroup TO analyst")
    op.execute("GRANT SELECT ON program_surveygroup TO analyst")
    op.execute("GRANT SELECT ON id_map TO analyst")


def downgrade():
    op.execute("REVOKE SELECT ON id_map FROM analyst")
    op.execute("REVOKE SELECT ON program_surveygroup FROM analyst")
    op.execute("REVOKE SELECT ON user_surveygroup FROM analyst")
    op.execute("REVOKE SELECT ON organisation_surveygroup FROM analyst")
    op.execute("REVOKE SELECT ON activity_surveygroup FROM analyst")

    op.drop_table('id_map')
    op.drop_table('program_surveygroup')
    op.drop_table('user_surveygroup')
    op.drop_table('organisation_surveygroup')
    op.drop_table('activity_surveygroup')
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
