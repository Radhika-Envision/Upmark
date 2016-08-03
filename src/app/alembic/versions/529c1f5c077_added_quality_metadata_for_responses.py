"""Added quality metadata for responses

Revision ID: 529c1f5c077
Revises: 21698752c39
Create Date: 2016-08-03 15:53:53.404904

"""

# revision identifiers, used by Alembic.
revision = '529c1f5c077'
down_revision = '21698752c39'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


survey = sa.sql.table('survey',
    sa.sql.column('has_quality', sa.Boolean)
)


def upgrade():
    op.add_column('response', sa.Column('quality', sa.Float()))
    op.add_column('response_history', sa.Column('quality', sa.Float()))
    op.add_column('survey', sa.Column('has_quality', sa.Boolean()))
    op.execute(survey.update().values({'has_quality': False}))
    op.alter_column('survey', 'has_quality', nullable=False)


def downgrade():
    op.drop_column('survey', 'has_quality')
    op.drop_column('response_history', 'quality')
    op.drop_column('response', 'quality')
