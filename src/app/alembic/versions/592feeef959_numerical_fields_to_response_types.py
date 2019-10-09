"""Numerical fields to response types

Revision ID: 592feeef959
Revises: 529c1f5c077
Create Date: 2016-08-03 02:27:08.843497

"""

# revision identifiers, used by Alembic.
revision = '592feeef959'
down_revision = '529c1f5c077'
branch_labels = None
depends_on = None

import copy
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from old_deps.guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


def upgrade():
    session = Session(bind=op.get_bind())
    for s in session.query(Survey).all():
        rts = copy.deepcopy(s._response_types)
        for rt in rts:
            for part in rt['parts']:
                part['type'] = 'multiple_choice'
        s._response_types = rts
    session.flush()


def downgrade():
    session = Session(bind=op.get_bind())
    for s in session.query(Survey).all():
        rts = copy.deepcopy(s._response_types)
        for rt in rts:
            for part in rt['parts']:
                del part['type']
        s._response_types = rts
    session.flush()


# Frozen model
class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    _response_types = Column('response_types', JSON, nullable=False)
