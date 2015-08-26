"""Removed attachments field from response table

Revision ID: 3d04b267d64
Revises: 47cbc89b3d0
Create Date: 2015-08-26 15:57:59.849701

"""

# revision identifiers, used by Alembic.
revision = '3d04b267d64'
down_revision = '47cbc89b3d0'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from guid import GUID
from history_meta import Versioned


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class Response(Versioned, Base):
    __tablename__ = 'response'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    attachments = Column(JSON)


ResponseHistory = Response.__history_mapper__.class_


def upgrade():
    op.drop_column('response', 'attachments')
    op.drop_column('response_history', 'attachments')


def downgrade():
    op.add_column('response_history', sa.Column('attachments', JSON))
    op.add_column('response', sa.Column('attachments', JSON))

    session = Session(bind=op.get_bind())
    for response in session.query(Response).all():
        response.attachments = []
    for response in session.query(ResponseHistory).all():
        response.attachments = []
    session.flush()

    op.alter_column('response_history', 'attachments', nullable=False)
    op.alter_column('response', 'attachments', nullable=False)
