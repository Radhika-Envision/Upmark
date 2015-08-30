"""Hierarchy ID is now non-null

Revision ID: e8a44a8f02
Revises: 2223adafa6a
Create Date: 2015-08-12 13:08:23.741253

"""

# revision identifiers, used by Alembic.
revision = 'e8a44a8f02'
down_revision = '2223adafa6a'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import foreign, relationship, remote, sessionmaker
from sqlalchemy.schema import ForeignKeyConstraint, MetaData
from sqlalchemy.sql.expression import and_

from guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


class QuestionNode(Base):
    # Frozen schema
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID, nullable=False)
    parent_id = Column(GUID)

    __table_args__ = (
        ForeignKeyConstraint(
            ['parent_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
    )


QuestionNode.parent = relationship(
    QuestionNode, backref='children',
    primaryjoin=and_(foreign(QuestionNode.parent_id) == remote(QuestionNode.id),
                     QuestionNode.survey_id == remote(QuestionNode.survey_id)))


def upgrade():
    session = Session(bind=op.get_bind())

    op.drop_constraint('qnode_root_check', 'qnode', type_='check')

    def get_hid(qnode):
        if qnode.hierarchy_id is not None:
            return qnode.hierarchy_id
        else:
            return get_hid(qnode.parent)

    for qnode in session.query(QuestionNode).all():
        qnode.hierarchy_id = get_hid(qnode)
    session.flush()

    op.alter_column('qnode', 'hierarchy_id', nullable=False)


def downgrade():
    session = Session(bind=op.get_bind())

    op.alter_column('qnode', 'hierarchy_id', nullable=True)

    for qnode in session.query(QuestionNode).all():
        if qnode.parent is not None:
            qnode.hierarchy_id = None
    session.flush()

    op.create_check_constraint(
        'qnode_root_check', 'qnode',
        '(parent_id IS NULL AND hierarchy_id IS NOT NULL) OR '
        '(parent_id IS NOT NULL AND hierarchy_id IS NULL)')
