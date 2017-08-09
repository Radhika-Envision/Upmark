__all__ = [
    'IdMap',
]

from sqlalchemy import Column


from .base import Base
from .guid import GUID


class IdMap(Base):
    '''
    Stores changes to entity IDs. Used rarely.
    '''
    __tablename__ = 'id_map'
    old_id = Column(GUID, default=GUID.gen, nullable=False, primary_key=True)
    new_id = Column(GUID, default=GUID.gen, nullable=False)
