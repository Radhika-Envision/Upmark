"""amcv new org meta asset types

Revision ID: a8ae1a2e2b16
Revises: cbfb418472ef
Create Date: 2017-08-30 03:35:29.628710

"""

# revision identifiers, used by Alembic.
revision = 'a8ae1a2e2b16'
down_revision = 'cbfb418472ef'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

def upgrade():
    op.drop_constraint('org_meta_asset_types_check', 'org_meta', type_='check')
    op.create_check_constraint(
        'org_meta_asset_types_check', 'org_meta',
        """asset_types <@ ARRAY[
            'water wholesale', 'water local',
            'wastewater wholesale', 'wastewater local',
            'stormwater', 'highway bridge', 'roads', 'rail', 'ports', 'airports'
        ]::varchar[]""")

def downgrade():
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'stormwater')
    """)
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'highway bridge')
    """)
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'roads')
    """)
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'rail')
    """)
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'ports')
    """)
    op.execute("""
        UPDATE org_meta
        SET asset_types = array_remove(asset_types, 'airports')
    """)
    op.drop_constraint('org_meta_asset_types_check', 'org_meta', type_='check')
    op.create_check_constraint(
        'org_meta_asset_types_check', 'org_meta',
        """asset_types <@ ARRAY[
            'water wholesale', 'water local',
            'wastewater wholesale', 'wastewater local'
        ]::varchar[]""")
