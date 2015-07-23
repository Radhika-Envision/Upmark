import datetime
import re
import time
import uuid

import model

import sqlalchemy
from sqlalchemy.orm import joinedload


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
        if value in self.visited:
            raise UtilException(
                "Serialisation failed: cycle detected: %s" % path)
        self.visited.append(value)

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
            son = time.mktime(value.timetuple())
        elif isinstance(value, uuid.UUID):
            son = str(value)
        elif hasattr(value, '__getitem__') and hasattr(value, 'keys'):
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
        if self.include is not None:
            if not any(item.search(path) for item in self.include):
                return False
        if self.exclude is not None:
            if any(item.search(path) for item in self.exclude):
                return False
        return True


def to_dict(ob, include=None, exclude=None,
            autonormalise=True, autosimplify=True):
    '''
    Convert the public fields of an object into a dictionary.
    '''
    names = [name for name in dir(ob)
        if not name.startswith('_')
        and not name == 'metadata']
    if include is not None:
        names = [name for name in names if name in include]
    elif exclude is not None:
        names = [name for name in names if name not in exclude]
    son = {name: getattr(ob, name) for name in names
        if not hasattr(getattr(ob, name), '__call__') }

    if autonormalise:
        son = normalise(son)
    if autosimplify:
        son = simplify(son)

    return son


def simplify(value):
    '''
    Convert the values in a dictionary to primitive types.
    '''
    if isinstance(value, str):
        return value
    elif isinstance(value, datetime.date):
        return time.mktime(value.timetuple())
    elif isinstance(value, uuid.UUID):
        return str(value)
    elif hasattr(value, '__getitem__') and hasattr(value, 'items'):
        return {k: simplify(v) for k, v in value.items()}
    elif hasattr(value, '__getitem__') and hasattr(value, '__iter__'):
        return [simplify(v) for v in value]
    else:
        return value


def to_camel_case(name):
    components = name.split('_')
    components = [components[0]] + [c.title() for c in components[1:]]
    return ''.join(components)


def normalise(value):
    '''
    Convert the keys of a JSON-like object to JavaScript form (camel case).
    '''
    if isinstance(value, str):
        return value
    elif hasattr(value, '__getitem__') and hasattr(value, 'items'):
        return {to_camel_case(k): normalise(v) for k, v in value.items()}
    elif hasattr(value, '__getitem__') and hasattr(value, '__iter__'):
        return [normalise(v) for v in value]
    else:
        return value


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


def updater(model):
    '''
    Sets fields of a mapped object to a value in a dictionary with the same
    name - or resets it to the column's default value if it's not in the
    dictionary.
    '''
    def update(name, son):
        if name in son:
            if getattr(self.model, name) != son['name']:
                setattr(self.model, name, son[name])
        else:
            column = getattr(self.model.__class__, name)
            if getattr(self.model, name) != column.default:
                setattr(self.model, name, column.default)
    return update


def get_current_survey():
    with model.session_scope() as session:
        survey = session.query(model.Survey).order_by(sqlalchemy.desc(model.Survey.created))[0]
        return survey.id


def is_current_survey(survey_id):
    return survey_id == str(get_current_survey())


def reorder(collection, son):
    '''
    Update the order of items in an `ordering_list` according to a serialised
    list.
    '''
    current = {str(m.id): m.seq for m in collection}
    proposed = {m['id']: m['seq'] for m in son}
    if current != proposed:
        raise handlers.MethodError(
            "The proposed changes are not compatible with the " +
            "current sequence.")

    order = {m['id']: i for i, m in enumerate(son)}
    collection.sort(key=lambda m: order[str(m.id)])
    collection.reorder()
