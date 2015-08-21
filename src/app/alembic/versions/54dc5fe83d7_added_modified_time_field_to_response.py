"""Added modified time field to response

Revision ID: 54dc5fe83d7
Revises: fd898b4714
Create Date: 2015-08-21 03:31:54.230850

"""

# revision identifiers, used by Alembic.
revision = '54dc5fe83d7'
down_revision = 'fd898b4714'
branch_labels = None
depends_on = None

import datetime
import uuid

from alembic import op
import sqlalchemy as sa

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, DateTime, Text
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


class Response(Versioned, Base):
    __tablename__ = 'response'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)

    modified = Column(DateTime, nullable=False)


ResponseHistory = Response.__history_mapper__.class_


def upgrade():
    op.add_column('response', sa.Column('modified', sa.DateTime()))
    op.add_column('response_history', sa.Column('modified', sa.DateTime()))

    session = Session(bind=op.get_bind())
    for r in session.query(Response).all():
        r.modified = datetime.datetime.now()
    for r in session.query(ResponseHistory).all():
        r.modified = datetime.datetime.now()

    op.alter_column('response', 'modified', nullable=False)
    op.alter_column('response_history', 'modified', nullable=False)


def downgrade():
    op.drop_column('response_history', 'modified')
    op.drop_column('response', 'modified')
