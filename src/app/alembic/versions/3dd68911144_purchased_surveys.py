"""Purchased surveys

Revision ID: 3dd68911144
Revises: cb93e2f734
Create Date: 2015-09-09 14:19:19.745033

"""

# revision identifiers, used by Alembic.
revision = '3dd68911144'
down_revision = 'cb93e2f734'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

import guid


def upgrade():
    op.create_table('purchased_survey',
        sa.Column('survey_id', guid.GUID(), nullable=False),
        sa.Column('hierarchy_id', guid.GUID(), nullable=False),
        sa.Column('organisation_id', guid.GUID(), nullable=False),
        sa.Column('open_date', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id'], ),
        sa.ForeignKeyConstraint(
            ['organisation_id'],
            ['organisation.id'], ),
        sa.PrimaryKeyConstraint('survey_id', 'hierarchy_id', 'organisation_id')
    )


def downgrade():
    op.drop_table('purchased_survey')
