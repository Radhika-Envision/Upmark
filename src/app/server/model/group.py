__all__ = [
    'Group',
]

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, func, Index, Text

from .base import Base
from .guid import GUID
from .observe import Observable


class Group(Observable, Base):
    __tablename__ = 'survey_group'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index('group_title_key', func.lower(title), unique=True),
    )

    @property
    def ob_type(self):
        return 'group'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self]

    def __repr__(self):
        return "Group(title={})".format(self.title)
