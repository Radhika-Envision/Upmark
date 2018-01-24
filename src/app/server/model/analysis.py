__all__ = [
    'CustomQuery',
    'CustomQueryHistory',
    'create_analyst_user',
    'drop_analyst_user',
    'reset_analyst_password',
    'store_analyst_password',
]

import base64
from datetime import datetime
import os

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKeyConstraint


from .base import Base
from .config import SystemConfig
from .connection import session_scope
from .guid import GUID
from .history_meta import Versioned
from .observe import Observable
from .user import AppUser


class CustomQuery(Observable, Versioned, Base):
    '''
    Stored database queries
    '''
    __tablename__ = 'custom_query'
    id = Column(GUID, default=GUID.gen, nullable=False, primary_key=True)
    modified = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(GUID, ForeignKey("appuser.id"), nullable=False)
    title = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    description = Column(Text)
    deleted = Column(Boolean, default=False, nullable=False)
    is_parameterised = Column(Boolean, default=False, nullable=False)

    user = relationship(AppUser)

    @property
    def ob_type(self):
        return 'custom_query'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self]

    @property
    def surveygroups(self):
        return set()

    __table_args__ = (
        ForeignKeyConstraint(
            ['user_id'],
            ['appuser.id'],
            info={'version': True}
        ),
    )


CustomQueryHistory = CustomQuery.__history_mapper__.class_
CustomQueryHistory.ob_type = property(lambda self: 'custom_query')
# CustomQueryHistory.user = relationship(AppUser, passive_deletes=True)
# CustomQueryHistory.user.set_parent(CustomQueryHistory, True)


def create_analyst_user():
    '''
    For arbitary queries on the web, create a new user named 'analyst'
    and give SELECT permission to all tables except the appuser.password
    column.
    '''

    with session_scope() as session:
        password = base64.b32encode(os.urandom(30)).decode('ascii')
        store_analyst_password(password, session)
        session.execute(
            "CREATE USER analyst WITH PASSWORD :pwd", {'pwd': password})
        session.execute(
            "GRANT USAGE ON SCHEMA public TO analyst")
        session.execute(
            "GRANT SELECT"
            " (id, organisation_id, email, name, role, created, deleted,"
            "  email_time, email_interval)"
            " ON appuser TO analyst")
        for table in Base.metadata.tables:
            if str(table) not in {
                    'appuser', 'systemconfig', 'alembic_version'}:
                session.execute(
                    "GRANT SELECT ON {} TO analyst".format(table))


def drop_analyst_user():
    with session_scope() as session:
        rs = session.execute(
            "SELECT count(*) FROM pg_roles WHERE rolname = 'analyst'")
        if rs.first()[0] > 0:
            session.execute("DROP OWNED BY analyst CASCADE")
            session.execute("DROP ROLE analyst")


def reset_analyst_password():
    with session_scope() as session:
        password = base64.b32encode(os.urandom(30)).decode('ascii')
        store_analyst_password(password, session)
        session.execute(
            "ALTER ROLE analyst WITH PASSWORD :pwd", {'pwd': password})


def store_analyst_password(password, session):
    pwd_conf = session.query(SystemConfig).get('_analyst_password')
    if pwd_conf is None:
        pwd_conf = SystemConfig(name='_analyst_password')
        pwd_conf.human_name = "Analyst password"
        pwd_conf.description = "Password for read-only database access"
        pwd_conf.user_defined = False
        session.add(pwd_conf)
    pwd_conf.value = password
