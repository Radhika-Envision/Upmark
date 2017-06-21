__all__ = ['Base', 'ModelError', 'to_id']

import uuid

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import MetaData


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


def to_id(ob_or_id):
    if ob_or_id is None:
        return None
    if isinstance(ob_or_id, (str, uuid.UUID)):
        return ob_or_id
    return ob_or_id.id
