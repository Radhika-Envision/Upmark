"""Added rnode table

Revision ID: 2223adafa6a
Revises: 145f93a3f88
Create Date: 2015-08-09 14:44:57.539481

"""

# revision identifiers, used by Alembic.
revision = '2223adafa6a'
down_revision = '145f93a3f88'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import old_deps.guid as guid


def upgrade():
    op.create_table('rnode',
        sa.Column('id', guid.GUID(), nullable=False),
        sa.Column('survey_id', guid.GUID(), nullable=False),
        sa.Column('assessment_id', guid.GUID(), nullable=False),
        sa.Column('qnode_id', guid.GUID(), nullable=False),
        sa.Column('n_submitted', sa.Integer(), nullable=False),
        sa.Column('n_reviewed', sa.Integer(), nullable=False),
        sa.Column('n_approved', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['assessment_id'],
            ['assessment.id']),
        sa.ForeignKeyConstraint(
            ['qnode_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']),
        sa.ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.add_column('assessment', sa.Column(
        'title', sa.Text(), nullable=True))
    op.add_column('response', sa.Column(
        'attachments', postgresql.JSON(), nullable=False))
    op.add_column('response_history', sa.Column(
        'attachments', postgresql.JSON(), nullable=False))

    op.alter_column('assessment', 'approval', type_=sa.Enum(
        'draft', 'final', 'reviewed', 'approved', native_enum=False))


def downgrade():
    op.alter_column('assessment', 'approval', type_=sa.Text)
    op.drop_column('response_history', 'attachments')
    op.drop_column('response', 'attachments')
    op.drop_column('assessment', 'title')
    op.drop_table('rnode')
