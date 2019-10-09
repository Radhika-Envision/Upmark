"""rnode and response action types

Revision ID: 37e7e2791e9
Revises: 57d1655cd25
Create Date: 2015-12-02 00:49:17.179213

"""

# revision identifiers, used by Alembic.
revision = '37e7e2791e9'
down_revision = '57d1655cd25'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy import column, func
from sqlalchemy.dialects.postgresql import array, ARRAY, TEXT
from sqlalchemy.sql.expression import cast


def upgrade():
    op.drop_constraint(
        'activity_ob_type_check', 'activity', type_='check')
    op.drop_constraint(
        'subscription_ob_type_check', 'subscription', type_='check')

    ob_types = array([
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure',
        'submission', 'rnode', 'response'], type_=TEXT)
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))


def downgrade():
    op.drop_constraint(
        'activity_ob_type_check', 'activity', type_='check')
    op.drop_constraint(
        'subscription_ob_type_check', 'subscription', type_='check')

    ob_types = array([
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure',
        'submission'])
    op.create_check_constraint(
        'activity_ob_type_check', 'activity',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
    op.create_check_constraint(
        'subscription_ob_type_check', 'subscription',
        cast(column('ob_type'), TEXT) == func.any(ob_types))
