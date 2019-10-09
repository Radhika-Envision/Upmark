"""Qnodes track descendant measures

Revision ID: 33f62cbfc5c
Revises: e8a44a8f02
Create Date: 2015-08-18 11:16:41.913020

"""

# revision identifiers, used by Alembic.
revision = '33f62cbfc5c'
down_revision = 'e8a44a8f02'
branch_labels = None
depends_on = None

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Boolean, create_engine, Column, DateTime, Enum, Float, \
    ForeignKey, Index, Integer, String, Text, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import backref, foreign, relationship, remote, sessionmaker
from sqlalchemy.schema import ForeignKeyConstraint, MetaData
from sqlalchemy.sql.expression import and_

from old_deps.guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()

class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)

    def update_stats_descendants(self):
        '''Updates the stats of an entire tree.'''
        for hierarchy in self.hierarchies:
            hierarchy.update_stats_descendants()


class Hierarchy(Base):
    __tablename__ = 'hierarchy'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey('survey.id'), nullable=False, primary_key=True)

    n_measures = Column(Integer, default=0, nullable=False)

    def update_stats(self):
        '''Updates the stats this hierarchy.'''
        n_measures = sum(qnode.n_measures for qnode in self.qnodes)
        self.n_measures = n_measures

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for qnode in self.qnodes:
            qnode.update_stats_descendants()
        self.update_stats()


class QuestionNode(Base):
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID, nullable=False)
    parent_id = Column(GUID)

    seq = Column(Integer)
    n_measures = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ['parent_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
        ForeignKeyConstraint(
            ['hierarchy_id', 'survey_id'],
            ['hierarchy.id', 'hierarchy.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
    )

    survey = relationship(Survey)

    def update_stats_ancestors(self):
        '''Updates the stats this node, and all ancestors.'''
        n_measures = len(self.measures)
        n_measures += sum(child.n_measures for child in self.children)
        self.n_measures = n_measures
        if self.parent is not None:
            self.parent.update_stats_ancestors()
        else:
            self.hierarchy.update_stats()

    def update_stats_descendants(self):
        '''Updates the stats of an entire subtree.'''
        for child in self.children:
            child.update_stats_descendants()
        n_measures = len(self.measures)
        n_measures += sum(child.n_measures for child in self.children)
        self.n_measures = n_measures


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)

    survey = relationship(
        Survey, backref=backref('measures', passive_deletes=True))


class QnodeMeasure(Base):
    # This is an association object for qnodes <-> measures. Normally this would
    # be done with a raw table, but because we want access to the `seq` column,
    # it needs to be a mapped class.
    __tablename__ = 'qnode_measure_link'
    survey_id = Column(GUID, nullable=False, primary_key=True)
    qnode_id = Column(GUID, nullable=False, primary_key=True)
    measure_id = Column(GUID, nullable=False, primary_key=True)

    seq = Column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ['qnode_id', 'survey_id'],
            ['qnode.id', 'qnode.survey_id']
        ),
        ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
    )


Survey.hierarchies = relationship(
    Hierarchy, backref="survey", viewonly=True)

Hierarchy.qnodes = relationship(
    QuestionNode, backref='hierarchy', viewonly=True,
    primaryjoin=and_(and_(foreign(QuestionNode.hierarchy_id) == Hierarchy.id,
                          QuestionNode.survey_id == Hierarchy.survey_id),
                     QuestionNode.parent_id == None))

QuestionNode.parent = relationship(
    QuestionNode, backref='children', viewonly=True,
    primaryjoin=and_(foreign(QuestionNode.parent_id) == remote(QuestionNode.id),
                     QuestionNode.survey_id == remote(QuestionNode.survey_id)))

QuestionNode.qnode_measures = relationship(
    QnodeMeasure, backref='qnode', viewonly=True,
    primaryjoin=and_(foreign(QnodeMeasure.qnode_id) == QuestionNode.id,
                     QnodeMeasure.survey_id == QuestionNode.survey_id))

Measure.qnode_measures = relationship(
    QnodeMeasure, backref='measure', viewonly=True,
    primaryjoin=and_(foreign(QnodeMeasure.measure_id) == Measure.id,
                     QnodeMeasure.survey_id == Measure.survey_id))

QuestionNode.measures = association_proxy('qnode_measures', 'measure')
QuestionNode.measure_seq = association_proxy('qnode_measures', 'seq')
Measure.parents = association_proxy('qnode_measures', 'qnode')


def upgrade():
    op.add_column('hierarchy', sa.Column('n_measures', sa.Integer()))
    op.add_column('qnode', sa.Column('n_measures', sa.Integer()))

    session = Session(bind=op.get_bind())
    surveys = session.query(Survey).all()
    for survey in surveys:
        survey.update_stats_descendants()
    session.flush()

    op.alter_column('hierarchy', 'n_measures', nullable=False)
    op.alter_column('qnode', 'n_measures', nullable=False)


def downgrade():
    op.drop_column('qnode', 'n_measures')
    op.drop_column('hierarchy', 'n_measures')
