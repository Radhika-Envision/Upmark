from contextlib import contextmanager
import os

from sqlalchemy.orm import sessionmaker

import model


SessionStaging = None
SessionUpstream = None


def connect_db():
    global SessionStaging, SessionUpstream
    engine_source = model.connect_db(
        'postgresql://postgres:postgres@%s:5432/postgres' %
        os.environ['SOURCE'])
    engine_target = model.connect_db(
        'postgresql://postgres:postgres@%s:5432/postgres' %
        os.environ['TARGET'])

    SessionStaging = sessionmaker(bind=engine_source)
    SessionUpstream = sessionmaker(bind=engine_target)


@contextmanager
def scope(db):
    # http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """Provide a transactional scope around a series of operations."""
    if db == 'rw_staging':
        session = SessionStaging()
    elif db == 'ro_upstream':
        session = SessionUpstream()
    else:
        raise ValueError

    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
