__all__ = ['Base', 'ModelError', 'to_id']

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import MetaData

from .guid import is_guid


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class ModelError(Exception):
    pass


def to_id(ob_or_id):
    if ob_or_id is None:
        return None
    if is_guid(ob_or_id) or isinstance(ob_or_id, str):
        return ob_or_id
    return ob_or_id.id
