from contextlib import contextmanager
import os
import sys
import uuid

from sqlalchemy import Boolean, create_engine, Column, DateTime, Float, \
    ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy.exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import Index, MetaData
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
    value = Column(String, nullable=True)

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

    organisation = relationship(Organisation)

    def set_password(self, plaintext):
        self.password = sha256_crypt.encrypt(plaintext)

    def check_password(self, plaintext):
        return sha256_crypt.verify(plaintext, self.password)

    __table_args__ = (
        Index('appuser_email_key', func.lower(email), unique=True),
    )


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


class Function(Base):
    __tablename__ = 'function'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    seq = Column(Integer)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)


class Process(Base):
    __tablename__ = 'process'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    function_id = Column(GUID, ForeignKey('function.id'))
    seq = Column(Integer)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)

    survey = relationship("Survey", uselist=False)


class Subprocess(Base):
    __tablename__ = 'subprocess'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    process_id = Column(GUID, ForeignKey('process.id'))
    seq = Column(Integer)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)

    survey = relationship("Survey", uselist=False)


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    subprocess_id = Column(GUID, ForeignKey('subprocess.id'), nullable=True)
    seq = Column(Integer)
    title = Column(Text, nullable=False)
    weight = Column(Float, nullable=False)
    intent = Column(Text, nullable=True)
    inputs = Column(Text, nullable=True)
    scenario = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)
    response_type = Column(Text, nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)

    survey = relationship("Survey", uselist=False)

    def __repr__(self):
        return "Measure(%s - %s)" % (self.id, self.title)


class MeasureSet(Base):
    __tablename__ = 'measureset'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)
    title = Column(Text, nullable=False)
    measures = relationship(
        Measure,
        secondary='measureset_measure_link'
    )


class MeasureSetMeasureLink(Base):
    __tablename__ = 'measureset_measure_link'
    id = Column(Integer, primary_key=True, autoincrement=True)
    measureset_id = Column(GUID, ForeignKey('measureset.id'), nullable=False)
    measure_id = Column(GUID, ForeignKey('measure.id'), nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)


Survey.functions = relationship(
        'Function', order_by='Function.seq', backref="survey",
        collection_class=ordering_list('seq'), passive_deletes=True)
Function.processes = relationship(
        'Process', order_by='Process.seq', backref="function",
        collection_class=ordering_list('seq'), passive_deletes=True)
Process.subprocesses = relationship(
        'Subprocess', order_by='Subprocess.seq', backref="process",
        collection_class=ordering_list('seq'), passive_deletes=True)
Subprocess.measures = relationship(
        'Measure', order_by='Measure.seq', backref="subprocess",
        collection_class=ordering_list('seq'), passive_deletes=True)


class Response(Versioned, Base):
    __tablename__ = 'response'
    # Here we define columns for the table response
    # Notice that each column is also a normal Python instance attribute.
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    user_id = Column(GUID, ForeignKey('appuser.id'), nullable=False)
    assessment_id = Column(GUID, ForeignKey('assessment.id'), nullable=False)
    measure_id = Column(GUID, ForeignKey('measure.id'), nullable=False)
    comment = Column(Text, nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    response_parts = Column(Text, nullable=False)
    audit_reason = Column(Text, nullable=True)
    # TODO: Test modified field from history table.


class Assessment(Base):
    __tablename__ = 'assessment'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    organisation_id = Column(GUID, ForeignKey('organisation.id'), nullable=False)
    survey_id = Column(GUID, ForeignKey('survey.id'), nullable=False)
    measureset_id = Column(GUID, ForeignKey('measureset.id'), nullable=False)
    # TODO: Make this field an enum
    approval = Column(Text, nullable=False)
    created = Column(DateTime, default=func.now(), nullable=False)


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


if __name__ == '__main__':
    testing()
