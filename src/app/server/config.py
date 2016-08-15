import logging
import os

import model

from utils import get_package_dir


log = logging.getLogger('app.config')


# This SCHEMA defines configuration parameters that a user is allowed to modify.
# The application may store other things in the systemconfig table, but only
# these ones will be visible / editable.
# Paths are relative to app.py.
SCHEMA = {
    'pass_threshold': {
        'type': 'numerical',
        'min': 0.1,
        'max': 1.0,
        'default_value': 0.85,
    },

    'adhoc_timeout': {
        'type': 'numerical',
        'min': 0.0,
        'default_value': 1.5,
    },
    'adhoc_max_limit': {
        'type': 'numerical',
        'min': 0.0,
        'default_value': 2500,
    },

    'app_name_short': {
        'type': 'string',
        'default_value': "Upmark",
    },
    'app_name_long': {
        'type': 'string',
        'default_value': "Upmark",
    },

    'theme_logo': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/logo.svg",
    },
    'theme_icon_lg': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/icon-lg.svg",
    },
    'theme_icon_sm': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/icon-sm.svg",
    },

    'is_training': {
        'type': 'boolean',
        'default_value': False,
    },
}


def is_primitive(schema):
    return schema['type'] in {'numerical', 'string', 'boolean'}


def is_private(name, schema):
    return name.startswith('_')


def get_setting(session, name, force_default=False):
    schema = SCHEMA.get(name)
    if not schema:
        raise KeyError("No such setting %s" % name)

    if not force_default:
        setting = session.query(model.SystemConfig).get(name)
    else:
        setting = None

    if setting:
        if setting.value is not None:
            if schema['type'] == 'numerical':
                return float(setting.value)
            elif schema['type'] == 'boolean':
                return setting.value.lower() == 'true'
            else:
                return setting.value
        elif setting.data is not None:
            return setting.data
    elif 'default_value' in schema:
        return schema['default_value']
    elif 'default_file_path' in schema:
        path = os.path.join(get_package_dir(), schema['default_file_path'])
        with open(path, 'rb') as f:
            return f.read()

    raise KeyError("No such setting %s" % name)


def set_setting(session, name, value):
    schema = SCHEMA.get(name)
    if not schema:
        return

    setting = session.query(model.SystemConfig).get(name)
    if not setting:
        setting = model.SystemConfig(name=name)
        session.add(setting)

    if schema['type'] == 'numerical':
        minimum = schema.get('min', float('-inf'))
        if minimum > float(value):
            raise ValueError(
                "Setting %s must be at least %s" % (name, minimum))

        maximum = schema.get('max', float('inf'))
        if maximum < float(value):
            raise ValueError(
                "Setting %s must be at most %s" % (name, maximum))

    if is_primitive(schema):
        setting.value = str(value)
        setting.data = None
    else:
        setting.value = None
        setting.data = value


def reset_setting(session, name):
    setting = session.query(model.SystemConfig).get(name)
    if setting:
        session.delete(setting)
