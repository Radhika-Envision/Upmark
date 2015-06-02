import os
import sys
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import Index
from history_meta import Versioned, versioned_session

Base = declarative_base()
session = None
POSTGRES_TARGET_URL = 'postgresql://postgres:postgres@postgres/aquamark'
POSTGRES_DEFAULT_URL = 'postgresql://postgres:postgres@postgres/postgres'

class Response(Versioned, Base):
    __tablename__ = 'response'
    # Here we define columns for the table response
    # Notice that each column is also a normal Python instance attribute.
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(250), nullable=False)
    measure_id = Column(Integer, ForeignKey('measure.id'))
    user_id = Column(String(250), ForeignKey('wassuser.id'))

Index('response_index', Response.name)

class WassUser(Versioned, Base):
    __tablename__ = 'wassuser'
    id = Column(String(250), primary_key=True)
    name = Column(String(250), nullable=False)
    password = Column(String(250), nullable=False)
    #response = relationship("Response", uselist=False, backref="response")

class Measure(Versioned, Base):
    __tablename__ = 'measure'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(250), nullable=False)
    #response = relationship("Response", uselist=False, backref="measure")

def create_database(database_name):
    engine = create_engine(POSTGRES_DEFAULT_URL)
    conn = engine.connect()
    conn.execute("commit")
    conn.execute("CREATE DATABASE " + database_name)
    conn.close()
 
def get_session():
    db_url = os.environ.get('POSTGRES_URL', POSTGRES_TARGET_URL)
    engine = create_engine(db_url)
    conn = None
    try:
        conn = engine.connect()
    except:
        create_database("aquamark")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    versioned_session(Session)
    return Session()

def testing():
    testMeasure = Measure(name="How are you today?")
    session.add(testMeasure)
    testMeasure.name = "How old are you?"
    session.commit()
    testUser = WassUser(name="Jin Park", id="forjin", password="guesswhat")
    session.add(testUser)
    session.commit()
    testResponse = Response(name="Answer 1", measure_id=testMeasure.id, user_id=testUser.id)
    session.add(testResponse)
    session.commit()

def __init__():
    print("session creating")
    session = get_session()
    testing()