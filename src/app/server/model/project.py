__all__ = [
    'Project',
]

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, func, Index, Text

from .base import Base
from .guid import GUID
from .observe import Observable


class Project(Observable, Base):
    __tablename__ = 'project'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('project_title_key', func.lower(title), unique=True),
    )

    def __repr__(self):
        return "Project(title={})".format(self.title)
