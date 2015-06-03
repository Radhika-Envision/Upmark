# model/meta.py
from sqlalchemy import schema
from sqlalchemy.ext.declarative import declarative_base

__all__ = ["Session", "metadata", "BaseObject" ]

Session = None

metadata = schema.MetaData()
BaseObject = declarative_base(metadata=metadata)