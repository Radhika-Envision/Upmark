import os
import sys
import uuid
from sqlalchemy import Column, ForeignKey, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import Index, MetaData
from history_meta import Versioned, versioned_session
from sqlalchemy.dialects.postgresql import UUID
from guid import GUID

metadata = MetaData()
Base = declarative_base(metadata=metadata)
session = None
POSTGRES_TARGET_URL  = 'postgresql://postgres:postgres@postgres/aquamark'
POSTGRES_DEFAULT_URL = 'postgresql://postgres:postgres@postgres/postgres'

class Response(Versioned, Base):
    __tablename__ = 'response'
    # Here we define columns for the table response
    # Notice that each column is also a normal Python instance attribute.
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    user_id = Column(GUID, ForeignKey('wassuser.id'))
    assessment_id = Column(GUID, ForeignKey('assessment.id'))
    measure_id = Column(GUID, ForeignKey('measure.id'))
    comment = Column(String(256), nullable=False)
    not_relevant = Column(Boolean, nullable=False)
    response_parts = Column(String(1024), nullable=False)
    audit_reason = Column(String(1024), nullable=False)
    name = Column(String(128), nullable=False)

Index('response_index', Response.name)

class Assessment(Versioned, Base):
    __tablename__ = 'assessment'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    utility_id = Column(GUID, ForeignKey('utility.id'))
    survey_id = Column(GUID, ForeignKey('survey.id'))
    functionset_id = Column(GUID, ForeignKey('functionset.id'))
    title = Column(String(256), nullable=False)
    approval = Column(String(256), nullable=False)

class Utility(Versioned, Base):
    __tablename__ = 'utility'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    name = Column(String(128), nullable=False)
    url = Column(String(1024), nullable=False)
    region = Column(String(128), nullable=False)
    number_of_customers = Column(Integer, nullable=False)

class Survey(Versioned, Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    date = Column(Date, nullable=False)
    title = Column(String(256), nullable=False)

class WassUser(Versioned, Base):
    __tablename__ = 'wassuser'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    name = Column(String(128), nullable=False)
    password = Column(String(128), nullable=False)
    role = Column(String(128), nullable=False)
    utility_id = Column(GUID, ForeignKey('utility.id'))

class Survey(Versioned, Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    date = Column(Date, nullable=False)
    title = Column(String(256), nullable=False)

class FunctionSet(Versioned, Base):
    __tablename__ = 'functionset'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    survey_id = Column(GUID, ForeignKey('survey.id'))
    title = Column(String(256), nullable=False)

class Function(Versioned, Base):
    __tablename__ = 'function'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    seq = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(String(256), nullable=False)
    weight = Column(Float, nullable=False)

class Process(Versioned, Base):
    __tablename__ = 'process'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    function_id = Column(GUID, ForeignKey('function.id'))
    seq = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(String(256), nullable=False)
    weight = Column(Float, nullable=False)

class Subprocess(Versioned, Base):
    __tablename__ = 'subprocess'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    process_id = Column(GUID, ForeignKey('process.id'))
    seq = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(String(256), nullable=False)
    weight = Column(Float, nullable=False)

class Measure(Versioned, Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4(), primary_key=True)
    subprocess_id = Column(GUID, ForeignKey('subprocess.id'), nullable=True)
    seq = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    weight = Column(Float, nullable=False)
    intent = Column(String(256), nullable=False)
    inputs = Column(String(256), nullable=False)
    scenario = Column(String(256), nullable=False)
    questions = Column(String(256), nullable=False)
    response_type = Column(String(256), nullable=False)
    #response = relationship("Response", uselist=False, backref="measure")

def create_database(database_name):
    db_url = os.environ.get('POSTGRES_DEFAULT_URL', POSTGRES_DEFAULT_URL)
    print ("db_url2", db_url)
    engine = create_engine(db_url)
    conn = engine.connect()
    conn.execute("commit")
    conn.execute("CREATE DATABASE " + database_name)
    conn.close()
 
def get_session():
    pass

def testing():
    db_url = os.environ.get('POSTGRES_URL', POSTGRES_TARGET_URL)
    print ("db_url", db_url)
    engine = create_engine(db_url)
    conn = None
    try:
        conn = engine.connect()
    except:
        create_database("aquamark")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    versioned_session(Session)
    session = Session()
    testFunction = Function(seq=1, title="Function 1", description="Test Description", weight=1)
    session.add(testFunction)
    session.commit()
    testFunction.title="F1"
    session.commit()
    testProcess = Process(seq=1, title="Process 1", function_id=testFunction.id, description="Test Description", weight=1)
    session.add(testProcess)
    session.commit()
    testSubprocess = Subprocess(seq=1, title="Subprocess 1", process_id=testProcess.id, description="Test Description", weight=1)
    session.add(testSubprocess)
    session.commit()
    testMeasure = Measure(seq=1, title="How are you?", subprocess_id=testSubprocess.id, weight=1, intent="intent", inputs="inputs", scenario="scenario", questions="questions", response_type="1")
    session.add(testMeasure)
    testMeasure.name = "How old are you?"
    '''
    session.commit()
    testUser = WassUser(name="Jin Park", id="forjin", password="guesswhat")
    session.add(testUser)
    session.commit()
    testResponse = Response(name="Answer 1", measure_id=testMeasure.id, user_id=testUser.id)
    session.add(testResponse)
    '''
    session.commit()

print("session creating")
get_session()
testing()