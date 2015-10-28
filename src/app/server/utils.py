import datetime
import logging
import re
import time
import uuid

import model

import sqlalchemy
from sqlalchemy.orm import joinedload
from sqlalchemy.engine.result import RowProxy


log = logging.getLogger('app.utils')


def truthy(value):
    '''
    @return True if the value is a string like 'True' (etc), or the boolean True
    '''
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        try:
            value = int(value)
            return value != 0
        except ValueError:
            return value.lower() in {'true', 't', 'yes', 'y', '1'}
    elif isinstance(value, int):
        return value != 0
    else:
        raise ValueError("Can't convert value to boolean")


def falsy(value):
    '''
    @return True if the value is a string like 'True' (etc), or if it is the
    Boolean False
    '''
    return not truthy(value)


class UtilException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class ToSon:
    def __init__(self, include=None, exclude=None, omit=False):
        self.include = include and [re.compile(x) for x in include] or None
        self.exclude = exclude and [re.compile(x) for x in exclude] or None
        self.omit = omit
        self.visited = []

    def __call__(self, value, path=""):
        log.debug('Visiting %s', path)
        if value in self.visited:
            raise UtilException(
                "Serialisation failed: cycle detected: %s" % path)
        self.visited.append(value)
        log.debug('Type is  %s', value.__class__)

        if isinstance(value, model.Base):
            names = dir(value)

            son = {}
            for name in names:
                if not self.can_emit(name, path):
                    continue
                v = getattr(value, name)
                if self.omit and v is None:
                    continue
                if hasattr(v, '__call__'):
                    continue
                son[to_camel_case(name)] = self(v, "%s/%s" % (path, name))

        elif isinstance(value, str):
            son = value
        elif isinstance(value, datetime.date):
            son = value.timestamp()
        elif isinstance(value, uuid.UUID):
            son = str(value)
        elif (hasattr(value, '__getitem__') and hasattr(value, 'keys') and
              hasattr(value, 'values') and not isinstance(value, RowProxy)):
            # Dictionaries
            son = {}
            for name in value.keys():
                if not self.can_emit(name, path):
                    continue
                v = value[name]
                if self.omit and v is None:
                    continue
                son[to_camel_case(name)] = self(v, "%s/%s" % (path, name))

        elif hasattr(value, '__iter__'):
            # Lists
            son = []
            for i, v in enumerate(value):
                if not self.can_emit(i, path):
                    continue
                if self.omit and v is None:
                    continue
                son.append(self(v, "%s/%d" % (path, i)))
        else:
            son = value

        self.visited.pop()
        return son

    def can_emit(self, name, basepath):
        name = str(name)
        if name.startswith('_'):
            return False
        if name == 'metadata':
            return False

        path = "%s/%s" % (basepath, name)
        log.debug('Testing %s', path)
        if self.include is not None:
            if not any(item.search(path) for item in self.include):
                return False
        if self.exclude is not None:
            if any(item.search(path) for item in self.exclude):
                return False
        return True


def to_camel_case(name):
    components = name.split('_')
    components = [components[0]] + [c.title() for c in components[1:]]
    return ''.join(components)


CAMEL_PATTERN = re.compile(r'([^A-Z])([A-Z])')


def to_snake_case(name):
    return CAMEL_PATTERN.sub(r'\1_\2', name).lower()


def denormalise(value):
    '''
    Convert the keys of a JSON-like object to Python form (snake case).
    '''
    pattern = re.compile(r'([^A-Z])([A-Z])')

    if isinstance(value, str):
        return value
    elif hasattr(value, '__getitem__') and hasattr(value, 'items'):
        return {pattern.sub(r'\1_\2', k).lower(): denormalise(v)
                for k, v in value.items()}
    elif hasattr(value, '__getitem__') and hasattr(value, '__iter__'):
        return [denormalise(v) for v in value]
    else:
        return value


class updater:
    '''
    Sets fields of a mapped object to a value in a dictionary with the same
    name.
    '''

    NULLIFY = 0
    DEFAULT = 1
    SKIP = 2

    def __init__(self, model, on_absent=SKIP):
        self.model = model
        self.on_absent = on_absent

    def __call__(self, name, son, on_absent=None):
        if on_absent is None:
            on_absent = self.on_absent

        if name in son:
            value = son[name]
        elif on_absent == updater.NULLIFY:
            value = None
        elif on_absent == updater.DEFAULT:
            column = getattr(self.model.__class__, name)
            value = column.default
        else:
            return

        current_value = getattr(self.model, name)
        if isinstance(current_value, uuid.UUID):
            equal = str(current_value) == str(value)
        else:
            equal = current_value == value

        if not equal:
            log.debug('Setting %s: %s -> %s', name, current_value, value)
            setattr(self.model, name, value)


def reorder(collection, son, id_attr='id'):
    '''
    Update the order of items in an `ordering_list` according to a serialised
    list.
    '''
    current = {str(getattr(m, id_attr)): m.seq for m in collection}
    proposed = {m['id']: m['seq'] for m in son}
    if current != proposed:
        raise handlers.MethodError(
            "The proposed changes are not compatible with the "
            "current sequence: items have been added or removed, or another "
            "user has changed the order too. Try reloading the list.")

    order = {m['id']: i for i, m in enumerate(son)}
    collection.sort(key=lambda m: order[str(getattr(m, id_attr))])
    collection.reorder()
