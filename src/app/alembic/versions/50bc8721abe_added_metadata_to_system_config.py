"""Added metadata to system config

Revision ID: 50bc8721abe
Revises: 412f89c7d08
Create Date: 2015-07-16 12:48:31.029916

"""

# revision identifiers, used by Alembic.
revision = '50bc8721abe'
down_revision = '412f89c7d08'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class SystemConfig(Base):
    '''Frozen schema'''
    __tablename__ = 'systemconfig'
    name = sa.Column(sa.String, primary_key=True)
    human_name = sa.Column(sa.String)
    user_defined = sa.Column(sa.Boolean)


def upgrade():
    session = Session(bind=op.get_bind())

    op.add_column('systemconfig', sa.Column('description', sa.String(), nullable=True))
    op.add_column('systemconfig', sa.Column('human_name', sa.String(), nullable=True))
    op.add_column('systemconfig', sa.Column('user_defined', sa.Boolean(), nullable=True))

    settings = session.query(SystemConfig).all()
    for setting in settings:
        setting.human_name = setting.name.replace('_', ' ').title()
        setting.user_defined = False
    session.flush()

    op.alter_column('systemconfig', 'human_name', nullable=False)
    op.alter_column('systemconfig', 'user_defined', nullable=False)


def downgrade():
    op.drop_column('systemconfig', 'user_defined')
    op.drop_column('systemconfig', 'human_name')
    op.drop_column('systemconfig', 'description')
