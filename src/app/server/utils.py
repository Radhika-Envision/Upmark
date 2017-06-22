import bleach
from collections import defaultdict
import datetime
import inspect
import logging
import os
import re
import time
import uuid
import yaml

from bunch import Bunch
import sqlalchemy
from sqlalchemy.orm import joinedload
from sqlalchemy.engine.result import RowProxy

import model


log = logging.getLogger('app.utils')


def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def get_config(file_name):
    file_path = os.path.join(get_package_dir(), '..', 'config', file_name)
    with open(file_path, 'r') as f:
        return yaml.load(f)


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
    def __init__(self, *expressions, omit=False):
        self._include = []
        self._exclude = []
        self._sanitise = []
        self.omit = omit
        self.visited = []
        self.add(*expressions)

    def add(self, *expressions):
        '''
        Add expressions for matching fields for serialisation. The expressions
        are evaluated against the path to the field. For example:
            - Any field called 'foo': r'/foo$'
            - Only 'foo' in the root object: r'^/foo$'
            - 'foo' in any direct child: r'^/\w/foo$'

        Fields can be excluded by prefixing the expression with a '!':
            - Never serialise a field called 'bar': r'!/bar$'

        Unsafe fields can be sanitised (HTML) by prefixing with '<':
            - Include and sanitise 'description' field: r'</description$'

        Prefix with a '\' if you want to use one of the other special characters
        at the start of the expression.
        '''
        for expression in expressions:
            if expression.startswith('<'):
                self._sanitise.append(re.compile(expression[1:]))
                self._include.append(re.compile(expression[1:]))
            elif expression.startswith('!'):
                self._exclude.append(re.compile(expression[1:]))
            elif expression.startswith(r'\\'):
                self._include.append(re.compile(expression[1:]))
            else:
                self._include.append(re.compile(expression))

    def exclude(self, *expressions):
        for expression in expressions:
            self._exclude.append(re.compile(expression))

    def __call__(self, value, path=""):
        log.debug('Visiting %s', path)
        if value in self.visited:
            raise UtilException(
                "Serialisation failed: cycle detected: %s" % path)
        self.visited.append(value)
        log.debug('Type is  %s', value.__class__)

        if isinstance(value, model.Base):
            names = dir(value)

            son = Bunch()
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
        elif isinstance(value, datetime.datetime):
            son = value.timestamp()
        elif isinstance(value, datetime.date):
            son = datetime.datetime.combine(
                value, datetime.datetime.min.time()).timestamp()
        elif isinstance(value, uuid.UUID):
            son = str(value)
        elif (hasattr(value, '__getitem__') and hasattr(value, 'keys') and
              hasattr(value, 'values') and not isinstance(value, RowProxy)):
            # Dictionaries
            son = Bunch()
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

        if isinstance(son, str) and any(s.search(path) for s in self._sanitise):
            son = bleach.clean(son, strip=True)

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
        if len(self._include) > 0:
            if not any(item.search(path) for item in self._include):
                return False
        if len(self._exclude) > 0:
            if any(item.search(path) for item in self._exclude):
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
        return Bunch((pattern.sub(r'\1_\2', k).lower(), denormalise(v))
                for k, v in value.items())
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

    def __init__(self, model, on_absent=SKIP, error_factory=ValueError):
        self.model = model
        self.on_absent = on_absent
        self.error_factory = error_factory

    def __call__(self, name, son, on_absent=None, sanitise=False):
        if on_absent is None:
            on_absent = self.on_absent

        current_value = getattr(self.model, name)
        if name in son:
            value = son[name]
            if sanitise:
                value = bleach.clean(value, strip=True)
        elif on_absent == updater.NULLIFY:
            value = None
        elif on_absent == updater.DEFAULT:
            column = getattr(self.model.__class__, name)
            value = column.default
        else:
            value = current_value

        self.validate(name, value)

        if isinstance(current_value, uuid.UUID):
            equal = str(current_value) == str(value)
        else:
            equal = current_value == value

        if equal:
            return

        log.debug('Setting %s: %s -> %s', name, current_value, value)
        setattr(self.model, name, value)

    def validate(self, name, value):
        if value is not None:
            return

        column = getattr(self.model.__class__, name)
        if not column.nullable:
            insp = sqlalchemy.inspect(self.model)
            if insp.persistent:
                # For persistent objects, column.default is not used.
                raise self.error_factory("Missing value for %s" % name)
            elif column.default is None:
                # Non-persistent objects are new; column.default will be used
                # when the session is flushed.
                raise self.error_factory("Missing value for %s" % name)


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


class keydefaultdict(defaultdict):
    # http://stackoverflow.com/a/2912455/320036
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)
            return ret
