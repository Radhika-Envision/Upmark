"""Added tracking ID to survey

Revision ID: 1ba14f036a
Revises: 28d059146a6
Create Date: 2015-08-06 06:53:54.135685

"""

# revision identifiers, used by Alembic.
revision = '1ba14f036a'
down_revision = '28d059146a6'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from old_deps.guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    tracking_id = Column(GUID, default=uuid.uuid4, nullable=False)


def upgrade():
    session = Session(bind=op.get_bind())
    op.add_column('survey', sa.Column('tracking_id', GUID, nullable=True))
    for survey in session.query(Survey).all():
        survey.tracking_id = uuid.uuid4()
    session.flush()
    op.alter_column('survey', 'tracking_id', nullable=False)


def downgrade():
    op.drop_column('survey', 'tracking_id')
