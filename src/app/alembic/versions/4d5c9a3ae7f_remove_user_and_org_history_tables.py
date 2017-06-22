"""Remove user and org history tables

Revision ID: 4d5c9a3ae7f
Revises: 54dc5fe83d7
Create Date: 2015-08-23 12:32:08.803472

"""

# revision identifiers, used by Alembic.
revision = '4d5c9a3ae7f'
down_revision = '54dc5fe83d7'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from old_deps.guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class Organisation(Base):
    __tablename__ = 'organisation'
    id = sa.Column(GUID, default=uuid.uuid4, primary_key=True)
    version = sa.Column('version', sa.INTEGER(), nullable=False)


class AppUser(Base):
    __tablename__ = 'appuser'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    version = sa.Column('version', sa.INTEGER(), nullable=False)


def upgrade():
    op.drop_table('appuser_history')
    op.drop_table('organisation_history')
    op.drop_column('appuser', 'version')
    op.drop_column('organisation', 'version')


def downgrade():
    op.add_column('organisation', sa.Column('version', sa.INTEGER()))
    op.add_column('appuser', sa.Column('version', sa.INTEGER()))

    session = Session(bind=op.get_bind())
    for org in session.query(Organisation).all():
        org.version = 1
    for user in session.query(AppUser).all():
        user.version = 1
    session.flush()

    op.alter_column('organisation', 'version', nullable=False)
    op.alter_column('appuser', 'version', nullable=False)

    op.create_table('organisation_history',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('name', sa.TEXT(), nullable=False),
        sa.Column('url', sa.TEXT()),
        sa.Column('region', sa.TEXT(), nullable=False),
        sa.Column('number_of_customers', sa.INTEGER(), nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(), nullable=False),
        sa.Column('version', sa.INTEGER(), nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP()),
        sa.PrimaryKeyConstraint(
            'id', 'version', name='organisation_history_pkey')
    )
    op.create_table('appuser_history',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('email', sa.TEXT(), nullable=False),
        sa.Column('name', sa.TEXT(), nullable=False),
        sa.Column('password', sa.TEXT(), nullable=False),
        sa.Column('role', sa.TEXT(), nullable=False),
        sa.Column('organisation_id', postgresql.UUID(), nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(), nullable=False),
        sa.Column('enabled', sa.BOOLEAN(), nullable=False),
        sa.Column('version', sa.INTEGER(), nullable=False),
        sa.Column('changed', postgresql.TIMESTAMP()),
        sa.PrimaryKeyConstraint(
            'id', 'version', name='appuser_history_pkey')
    )
