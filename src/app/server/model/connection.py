__all__ = [
    'connect_db',
    'connect_db_ro',
    'get_database_url',
    'MissingUser',
    'session_scope',
    'WrongPassword',
]

from contextlib import contextmanager
from itertools import count
import logging
import os
import time

from sqlalchemy import create_engine
import sqlalchemy.exc
from sqlalchemy.orm import sessionmaker

from .base import ModelError
from .config import SystemConfig
from .history_meta import versioned_session


log = logging.getLogger('app.model.connection')

Session = None
VersionedSession = None
ReadonlySession = None


@contextmanager
def session_scope(version=False, readonly=False):
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
    if readonly:
        session = ReadonlySession()
    elif version:
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


def get_database_url():
    host = os.environ['PGHOST']
    port = os.environ['PGPORT']
    username = os.environ['PGUSER']
    database = os.environ['PGDATABASE']
    password = os.environ['PGPASSWORD']
    return sqlalchemy.engine.url.URL(
        'postgresql',
        username=username,
        password=password,
        host=host,
        port=port,
        database=database)


def connect_db(url, max_attempts=5):
    global Session, VersionedSession
    for i in count():
        try:
            engine = create_engine(url)
            engine.execute('SELECT 1')
            break
        except sqlalchemy.exc.OperationalError:
            if i > max_attempts:
                log.error(
                    "Database connection failed after %d attempts.",
                    max_attempts)
                raise
            else:
                time.sleep(1)

    # Never drop the schema here.
    # - For short-term testing, use psql.
    # - For breaking changes, add migration code to the alembic scripts.
    Session = sessionmaker(bind=engine)
    VersionedSession = sessionmaker(bind=engine)
    versioned_session(VersionedSession)

    return engine


class MissingUser(ModelError):
    pass


class WrongPassword(ModelError):
    pass


def connect_db_ro(base_url):
    global ReadonlySession

    with session_scope() as session:
        count = (
            session.execute(
                '''SELECT count(*)
                   FROM pg_catalog.pg_user u
                   WHERE u.usename = :usename''',
                {'usename': 'analyst'})
            .scalar())
        if count != 1:
            raise MissingUser("analyst user does not exist")

        password = (
            session.query(SystemConfig.value)
            .filter(SystemConfig.name == '_analyst_password')
            .scalar())

    parsed_url = sqlalchemy.engine.url.make_url(base_url)
    readonly_url = sqlalchemy.engine.url.URL(
        parsed_url.drivername,
        username='analyst',
        password=password,
        host=parsed_url.host,
        port=parsed_url.port,
        database=parsed_url.database)
    engine_readonly = create_engine(readonly_url)
    ReadonlySession = sessionmaker(bind=engine_readonly)

    # Try to connect now so we know if the password is OK
    with session_scope(readonly=True) as session:
        try:
            session.execute('SELECT 1')
        except sqlalchemy.exc.OperationalError as e:
            raise WrongPassword(e)

    return engine_readonly
