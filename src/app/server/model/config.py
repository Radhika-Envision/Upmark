__all__ = ['SystemConfig']

from datetime import datetime

from sqlalchemy import Column, DateTime, String, LargeBinary

from .base import Base


class SystemConfig(Base):
    __tablename__ = 'systemconfig'
    name = Column(String, primary_key=True, nullable=False)
    value = Column(String)
    data = Column(LargeBinary)
    modified = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return "SystemConfig(name={}, value={})".format(self.name, self.value)
