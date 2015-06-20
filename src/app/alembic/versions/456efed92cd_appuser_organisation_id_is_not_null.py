"""AppUser.organisation_id is not null

Revision ID: 456efed92cd
Revises: 2ee8262273c
Create Date: 2015-06-20 08:39:23.341290

"""

# revision identifiers, used by Alembic.
revision = '456efed92cd'
down_revision = '2ee8262273c'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, Date, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import func

from guid import GUID
from history_meta import Versioned


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class Organisation(Versioned, Base):
    '''Old model (frozen)'''
    __tablename__ = 'organisation'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    region = Column(Text, nullable=False)
    number_of_customers = Column(Integer, nullable=False)
    created = Column(Date, default=func.now(), nullable=False)


class AppUser(Versioned, Base):
    '''Old model (frozen)'''
    __tablename__ = 'appuser'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    password = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=True)
    created = Column(Date, default=func.now(), nullable=False)


AppUserHistory = AppUser.__history_mapper__.class_


def upgrade():
    session = Session(bind=op.get_bind())
    count = session.query(func.count(AppUser.id)).\
            filter_by(organisation_id=None).scalar()
    count_hist = session.query(func.count(AppUserHistory.id)).\
            filter_by(organisation_id=None).scalar()
    if count > 0 or count_hist > 0:
        default_org = Organisation(
            name="DEFAULT", region="NOWHERE", number_of_customers=0)
        session.add(default_org)
        session.flush()
        session.query(AppUser).filter_by(organisation_id=None).\
                update({"organisation_id": default_org.id})
        session.query(AppUserHistory).filter_by(organisation_id=None).\
                update({"organisation_id": default_org.id})
        session.flush()

    op.alter_column(
        'appuser', 'organisation_id', existing_type=postgresql.UUID(),
        nullable=False)
    op.alter_column(
        'appuser_history', 'organisation_id', existing_type=postgresql.UUID(),
        nullable=False)
    op.create_foreign_key(
        None, 'assessment', 'organisation', ['organisation_id'], ['id'])
    op.create_foreign_key(
        None, 'response', 'appuser', ['user_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'response', type_='foreignkey')
    op.drop_constraint(None, 'assessment', type_='foreignkey')
    op.alter_column(
        'appuser_history', 'organisation_id', existing_type=postgresql.UUID(),
        nullable=True)
    op.alter_column(
        'appuser', 'organisation_id', existing_type=postgresql.UUID(),
        nullable=True)
