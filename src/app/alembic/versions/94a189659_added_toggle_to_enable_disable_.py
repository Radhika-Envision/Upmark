"""Added toggle to enable/disable aggregate scores

Revision ID: 94a189659
Revises: 330209405a1
Create Date: 2016-08-10 06:10:27.661545

"""

# revision identifiers, used by Alembic.
revision = '94a189659'
down_revision = '330209405a1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

survey = sa.sql.table('survey',
                      sa.sql.column('hide_aggregate', sa.Boolean))

def upgrade():
    op.add_column('survey', sa.Column('hide_aggregate', sa.Boolean()))
    op.execute(survey.update().values({'hide_aggregate': False}))
    op.alter_column('survey', 'hide_aggregate', nullable=False)


def downgrade():
    op.drop_column('survey', 'hide_aggregate')
