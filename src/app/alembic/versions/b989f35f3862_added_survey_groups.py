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

from alembic import op  # noqa: E402
import sqlalchemy as sa  # noqa: E402

import deps_b989f35f3862 as model  # noqa: E402


def upgrade():
    op.create_table(
        'survey_group',
        sa.Column('id', model.guid.GUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.drop_constraint('appuser_role_check', 'appuser', type_='check')
    op.create_check_constraint(
        'appuser_role_check', 'appuser',
        """role = ANY (ARRAY[
            'super_admin', 'admin', 'author', 'authority', 'consultant',
            'org_admin', 'clerk'
        ]::varchar[])""")


def downgrade():
    op.drop_table('survey_group')

    op.execute("""
        UPDATE appuser
        SET role = 'admin'
        WHERE role = 'super_admin'
    """)
    op.drop_constraint('appuser_role_check', 'appuser', type_='check')
    op.create_check_constraint(
        'appuser_role_check', 'appuser',
        """role = ANY (ARRAY[
            'admin', 'author', 'authority', 'consultant', 'org_admin', 'clerk'
        ]::varchar[])""")
