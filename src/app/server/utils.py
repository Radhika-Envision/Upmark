import datetime
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
            return value.lower() in {'true', 't', 'yes', 'y'}
    elif isinstance(value, int):
        return value != 0
    else:
        raise ValueError("Can't convert value to boolean")


def falsy(value):
    '''
    @return True if the value is a string like 'True' (etc), or if it is the boolean False
    '''
    return not truthy(value)



def to_dict(ob, include=None, exclude=None):
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
    return {name: getattr(ob, name) for name in names
        if not hasattr(getattr(ob, name), '__call__') }


def simplify(ob_dict):
    '''
    Convert the values in a dictionary to primitive types.
    '''
    new_dict = {}
    for name, value in ob_dict.items():
        if isinstance(value, datetime.date):
            value = time.mktime(value.timetuple())
        elif isinstance(value, uuid.UUID):
            value = str(value)
        new_dict[name] = value
    return new_dict


def normalise(ob_dict):
    '''
    Convert the keys of a dictionary to JSON form.
    '''
    new_dict = {}
    for name, value in ob_dict.items():
        components = name.split('_')
        if len(components) > 1 and components[-1] == 'id':
            components = components[:-1]
        components = [components[0]] + [c.title() for c in components[1:]]
        name = ''.join(components)
        new_dict[name] = value
    return new_dict


def denormalise(ob_dict):
    '''
    Convert the keys of a dictionary to Python form.
    '''
    new_dict = {}
    for name, value in ob_dict.items():
        new_name = ""
        for i, char in enumerate(name):
            if char.isupper():
                if i > 0:
                    new_name += '_'
                new_name += char.lower()
            else:
                new_name += char
        new_dict[new_name] = value
    return new_dict


def get_current_survey():
    with model.session_scope() as session:
        survey = session.query(model.Survey).order_by(sqlalchemy.desc(model.Survey.created))[0]
        return survey.id


def is_current_survey(survey_id):
    return survey_id == str(get_current_survey())


def get_model(is_current, model):
    if is_current:
        return model
    else:
        return model.__history_mapper__.class_
