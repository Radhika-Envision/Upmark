from contextlib import contextmanager
import os
import sys
import uuid

from sqlalchemy import create_engine, Column, ForeignKey, Integer, String, Float, Date, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy.exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import Index, MetaData
from passlib.hash import sha256_crypt

from .guid import GUID
from .history_meta import Versioned, versioned_session


SCHEMA_VERSION = '0.0.1'
DATABASE_URL  = 'postgresql://postgres:postgres@postgres/aquamark'
POSTGRES_DEFAULT_URL = 'postgresql://postgres:postgres@postgres/postgres'


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


class Response(Versioned, Base):
    __tablename__ = 'response'
    # Here we define columns for the table response
    # Notice that each column is also a normal Python instance attribute.
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    user_id = Column(GUID, ForeignKey('appuser.id'))
    assessment_id = Column(GUID, ForeignKey('assessment.id'))
    measure_id = Column(GUID, ForeignKey('measure.id'))
    comment = Column(Text, nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    response_parts = Column(Text, nullable=False)
    audit_reason = Column(Text, nullable=True)
    # TODO: Test modified field from history table.


class Assessment(Versioned, Base):
    __tablename__ = 'assessment'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    utility_id = Column(GUID, ForeignKey('utility.id'))
    survey_id = Column(GUID, ForeignKey('survey.id'))
    measureset_id = Column(GUID, ForeignKey('measureset.id'))
    # TODO: Make this field an enum
    approval = Column(Text, nullable=False)
    created = Column(Date, nullable=False)
    # TODO: Add created field


class Utility(Versioned, Base):
    __tablename__ = 'utility'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    url = Column(Text, nullable=True)
    region = Column(Text, nullable=False)
    number_of_customers = Column(Integer, nullable=False)
    created = Column(Date, nullable=False)
    # TODO: Add created field


class Survey(Versioned, Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    created = Column(Date, nullable=False)
    title = Column(Text, nullable=False)


class AppUser(Versioned, Base):
    __tablename__ = 'appuser'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    name = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False, unique=True)
    password = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    utility_id = Column(GUID, ForeignKey('utility.id'))
    created = Column(Date, default=func.now(), nullable=False)

    def set_password(self, plaintext):
        self.password = sha256_crypt.encrypt(plaintext)

    def check_password(self, plaintext):
        return sha256_crypt.verify(plaintext, self.password)


class Function(Versioned, Base):
    __tablename__ = 'function'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    seq = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class Process(Versioned, Base):
    __tablename__ = 'process'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    function_id = Column(GUID, ForeignKey('function.id'))
    seq = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class Subprocess(Versioned, Base):
    __tablename__ = 'subprocess'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    process_id = Column(GUID, ForeignKey('process.id'))
    seq = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)


class Measure(Versioned, Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    subprocess_id = Column(GUID, ForeignKey('subprocess.id'), nullable=True)
    seq = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    weight = Column(Float, nullable=False)
    intent = Column(Text, nullable=False)
    inputs = Column(Text, nullable=False)
    scenario = Column(Text, nullable=False)
    questions = Column(Text, nullable=False)
    response_type = Column(Text, nullable=False)
    #response = relationship("Response", uselist=False, backref="measure")


# TODO: Change this to MethodSet, and add many-to-many mapping to methods.
class MeasureSet(Base):
    __tablename__ = 'measureset'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    survey_id = Column(GUID, ForeignKey('survey.id'))
    title = Column(Text, nullable=False)
    measures = relationship(
        Measure,
        secondary='measureset_measure_link'
    )


class MeasureSetMeasureLink(Base):
    __tablename__ = 'measureset_measure_link'
    id = Column(Integer, primary_key=True, autoincrement=True)
    measureset_id = Column(GUID, ForeignKey('measureset.id'))
    measure_id = Column(GUID, ForeignKey('measure.id'))
    version = Column(Integer, nullable=True, default=None)


# TODO: I don't think this script should create the database. It should be done
# by an admin.
def create_database(database_name):
    db_url = os.environ.get('POSTGRES_DEFAULT_URL', POSTGRES_DEFAULT_URL)
    engine = create_engine(db_url)
    conn = engine.connect()
    conn.execute("commit")
    conn.execute("CREATE DATABASE " + database_name)
    conn.close()


Session = None


@contextmanager
def session_scope():
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
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
    #Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    versioned_session(Session)
    update_model()


def update_model():
    with session_scope() as session:
        try:
            q = session.query(SystemConfig)
            conf = q.filter_by(name='schema_version').one()
        except sqlalchemy.exc.SQLAlchemyError:
            conf = SystemConfig(name='schema_version', value=SCHEMA_VERSION)
            session.add(conf)

        current_version = conf.value.split('.')
        target_version = SCHEMA_VERSION.split('.')
        if current_version == target_version:
            return
        elif current_version > target_version:
            raise ModelError('Database schema version is not supported.')

        conf.value = SCHEMA_VERSION

        # When the schema changes, add migration code here. E.g.
        #if current_version < [0, 1, 0]:
        #    do_something()


# TODO: Separate these tests out into a different module. Use PyUnit.
# TODO: Add test that shows how to pull data out of the database.
# TODO: Add test that shows a failed transaction, with exception handling.
# TODO: Always use exception handling to ensure the session is closed:
#       http://docs.sqlalchemy.org/en/latest/orm/session_transaction.html#managing-transactions
#       Or use a context manager (preferred):
#       http://stackoverflow.com/a/29805305/320036
def testing():
    connect_db(os.environ.get('DATABASE_URL'))
    with session_scope() as session:
        testUser = AppUser(user_id="forjin", name="Jin", privileges="admin")
        testUser.set_password("test")
        session.add(testUser)
        assert testUser.check_password("Test")
    '''
    testFunction = Function(seq=1, title="Function 1", description="Test Description")
    session.add(testFunction)
    session.commit()
    testFunction.title="F1"
    session.commit()
    testProcess = Process(seq=1, title="Process 1", function_id=testFunction.id, description="Test Description")
    session.add(testProcess)
    session.commit()
    testSubprocess = Subprocess(seq=1, title="Subprocess 1", process_id=testProcess.id, description="Test Description")
    session.add(testSubprocess)
    session.commit()
    testMeasure = Measure(seq=1, title="How are you?", subprocess_id=testSubprocess.id, weight=1, intent="intent", inputs="inputs", scenario="scenario", questions="questions", response_type="1")
    session.add(testMeasure)
    testMeasure.name = "How old are you?"
    session.commit()
    testUser = AppUser(name="Jin Park", id="forjin", password="guesswhat")
    session.add(testUser)
    session.commit()
    testResponse = Response(name="Answer 1", measure_id=testMeasure.id, user_id=testUser.id)
    session.add(testResponse)
    '''
    session.commit()


if __name__ == '__main__':
    testing()
