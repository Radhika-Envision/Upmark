from contextlib import contextmanager
import os
import sys
import uuid

from sqlalchemy import Boolean, create_engine, Column, DateTime, Float, \
    ForeignKey, Index, Integer, String, Text, Table
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSON
import sqlalchemy.exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import ForeignKeyConstraint, Index, MetaData
from passlib.hash import sha256_crypt

from guid import GUID
from history_meta import Versioned, versioned_session


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


class SystemConfig(Base):
    __tablename__ = 'systemconfig'
    name = Column(String, primary_key=True, nullable=False)
    human_name = Column(String, nullable=False)
    user_defined = Column(Boolean, nullable=False)
    value = Column(String)
    description = Column(String)

    def __str__(self):
        return "SystemConfig(name={}, value={})".format(self.name, self.value)


class Organisation(Versioned, Base):
    __tablename__ = 'organisation'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    name = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    region = Column(Text, nullable=False)
    number_of_customers = Column(Integer, nullable=False)
    created = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index('organisation_name_key', func.lower(name), unique=True),
    )

    def __str__(self):
        return "Organisation(name={})".format(self.name)


class AppUser(Versioned, Base):
    __tablename__ = 'appuser'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    email = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    password = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)
    created = Column(DateTime, default=func.now(), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    def set_password(self, plaintext):
        self.password = sha256_crypt.encrypt(plaintext)

    def check_password(self, plaintext):
        return sha256_crypt.verify(plaintext, self.password)

    __table_args__ = (
        Index('appuser_email_key', func.lower(email), unique=True),
    )

    def __str__(self):
        return "AppUser(email={})".format(self.email)


Organisation.users = relationship(
    AppUser, backref="organisation", passive_deletes=True)


ROLE_HIERARCHY = {
    'admin': {'author', 'authority', 'consultant', 'org_admin', 'clerk'},
    'author': set(),
    'authority': {'consultant'},
    'consultant': set(),
    'org_admin': {'clerk'},
    'clerk': set()
}


def has_privillege(current_role, *target_roles):
    '''
    Checks whether one role has the privilleges of another role. For example,
        has_privillege('org_admin', 'clerk') -> True
        has_privillege('clerk', 'org_admin') -> False
        has_privillege('clerk', 'consultant', 'clerk') -> True
    '''
    for target_role in target_roles:
        if target_role == current_role:
            return True
        if target_role in ROLE_HIERARCHY[current_role]:
            return True
    return False


class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    created = Column(DateTime, default=func.now(), nullable=False)
    # Survey is not editable after being finalised.
    finalised_date = Column(DateTime)
    # Survey is not open for responses until after the open_date.
    open_date = Column(DateTime)
    title = Column(Text, nullable=False)
    description = Column(Text)

    @property
    def is_editable(self):
        return self.finalised_date is None

    @property
    def is_open(self):
        return self.open_date is not None

    def __str__(self):
        return "Survey(title={})".format(self.title)


class Hierarchy(Base):
    __tablename__ = 'hierarchy'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey('survey.id'), nullable=False, primary_key=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    structure = Column(JSON, nullable=False)

    children = relationship(
        lambda: QuestionNode, order_by='QuestionNode.seq', backref='hierarchy',
        collection_class=ordering_list('seq'), passive_deletes=True)

    def __str__(self):
        return "Hierarchy(title={}, survey={})".format(
            self.title, self.survey.title)


Survey.hierarchies = relationship(
    Hierarchy, backref="survey", passive_deletes=True)


class QuestionNode(Base):
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, nullable=False, primary_key=True)
    hierarchy_id = Column(GUID)
    parent_id = Column(GUID)
    seq = Column(Integer)

    # For branches only
    title = Column(Text)
    description = Column(Text)

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

    def __repr__(self):
        return "QuestionNode(title={}, survey={})".format(
            self.title, self.survey.title)


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)
    seq = Column(Integer)
    title = Column(Text, nullable=False)
    weight = Column(Float, nullable=False)
    intent = Column(Text, nullable=True)
    inputs = Column(Text, nullable=True)
    scenario = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)
    response_type = Column(Text, nullable=False)

    survey = relationship(Survey)

    def __repr__(self):
        return "Measure(title={}, survey={})".format(
            self.title, self.survey.title)


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

    survey = relationship(Survey)

    def __repr__(self):
        return "QnodeMeasure(title={}, survey={})".format(
            self.title, self.survey.title)


QuestionNode.children = relationship(
    QuestionNode, order_by='QuestionNode.seq', backref='parent',
    collection_class=ordering_list('seq'), passive_deletes=True,
    remote_side=[QuestionNode.id])


# Need to give explicit join rules due to use of foreign key in composite
# primary keys: QuestionNode.survey_id and Measure.survey_id.
# http://docs.sqlalchemy.org/en/rel_1_0/orm/join_conditions.html#overlapping-foreign-keys
QuestionNode.measures = relationship(
    Measure,
    primaryjoin="and_(qnode_measure_link.c.qnode_id == QuestionNode.id,"
                "qnode_measure_link.c.survey_id == foreign(QuestionNode.survey_id))",
    secondaryjoin="and_(qnode_measure_link.c.measure_id == Measure.id,"
                "qnode_measure_link.c.survey_id == foreign(Measure.survey_id))",
    secondary='qnode_measure_link',
    order_by='qnode_measure_link.c.seq',
    collection_class=ordering_list('seq'),
    backref='parents'
)


class Response(Versioned, Base):
    __tablename__ = 'response'
    # Here we define columns for the table response
    # Notice that each column is also a normal Python instance attribute.
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)
    user_id = Column(GUID, ForeignKey('appuser.id'), nullable=False)
    assessment_id = Column(GUID, ForeignKey('assessment.id'), nullable=False)
    measure_id = Column(GUID, nullable=False)
    comment = Column(Text, nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    response_parts = Column(Text, nullable=False)
    audit_reason = Column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ['measure_id', 'survey_id'],
            ['measure.id', 'measure.survey_id']
        ),
        ForeignKeyConstraint(
            ['survey_id'],
            ['survey.id']
        ),
    )

    survey = relationship(Survey)
    measure = relationship(Survey)

    def __repr__(self):
        return "QnodeMeasure(measure={}, survey={}, org={})".format(
            self.measure.title, self.survey.title,
            self.assessment.Organisation.name)


class Assessment(Base):
    __tablename__ = 'assessment'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)
    organisation_id = Column(GUID, ForeignKey('organisation.id'), nullable=False)
    hierarchy_id = Column(GUID, nullable=False)
    # TODO: Make this field an enum?
    approval = Column(Text, nullable=False)
    created = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
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
    organisation = relationship(Organisation)

    def __repr__(self):
        return "Assessment(survey={}, org={})".format(
            self.survey.title, self.assessment.Organisation.name)


Assessment.responses = relationship(
    Response, backref='assessment', passive_deletes=True,
    remote_side=[Assessment.id])


Session = None
VersionedSession = None


@contextmanager
def session_scope(version=False):
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
    if version:
        session = VersionedSession()
    else:
        session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def connect_db(url):
    global Session
    engine = create_engine(url)
    conn = engine.connect()
    # Never drop the schema here.
    # - For short-term testing, use psql.
    # - For breaking changes, add migration code to the alembic scripts.
    Session = sessionmaker(bind=engine)
    VersionedSession = sessionmaker(bind=engine)
    versioned_session(VersionedSession)
    return engine


def initialise_schema(engine):
    Base.metadata.create_all(engine)
