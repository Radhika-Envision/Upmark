from contextlib import contextmanager
from datetime import datetime
from itertools import count
import logging
import time

from sqlalchemy import create_engine
import sqlalchemy.exc
from sqlalchemy.orm import sessionmaker

from history_meta import versioned_session


from .activity import *
from .analysis import *
from .base import *
from .config import *
from .connection import *
from .submission import *
from .survey import *
from .user import *


def initialise_schema(engine):
    Base.metadata.create_all(engine)
    # Analyst user creation should be done here. Schema upgrades need to adjust
    # permissions of the analyst user, therefore that user is part of the
    # schema.
    create_analyst_user()