"""Added stats fields to response

Revision ID: fd898b4714
Revises: 33f62cbfc5c
Create Date: 2015-08-19 23:35:46.178577

"""

# revision identifiers, used by Alembic.
revision = 'fd898b4714'
down_revision = '33f62cbfc5c'
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


enum_type = sa.Enum(
    'draft', 'final', 'reviewed', 'approved', native_enum=False)


class Response(Versioned, Base):
    __tablename__ = 'response'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)

    score = Column(sa.Float, default=0.0)
    approval = Column(enum_type)


ResponseHistory = Response.__history_mapper__.class_


def upgrade():

    op.add_column('response', sa.Column('approval', enum_type))
    op.add_column('response', sa.Column('score', sa.Float()))
    op.add_column('response_history', sa.Column('approval', enum_type))
    op.add_column('response_history', sa.Column('score', sa.Float()))

    session = Session(bind=op.get_bind())
    for r in session.query(Response).all():
        r.score = 0.0
        r.approval = 'draft'
    for r in session.query(ResponseHistory).all():
        r.score = 0.0
        r.approval = 'draft'

    op.alter_column('response', 'score', nullable=False)
    op.alter_column('response', 'approval', nullable=False)
    op.alter_column('response_history', 'score', nullable=False)
    op.alter_column('response_history', 'approval', nullable=False)


def downgrade():
    op.drop_column('response_history', 'score')
    op.drop_column('response_history', 'approval')
    op.drop_column('response', 'score')
    op.drop_column('response', 'approval')
