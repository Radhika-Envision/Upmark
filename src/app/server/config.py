import logging
import os
from pathlib import Path

from expiringdict import ExpiringDict
import yaml

import theme
import model
from utils import get_package_dir


log = logging.getLogger('app.config')


# This SCHEMA defines configuration parameters that a user is allowed to
# modify. The application may store other things in the systemconfig table, but
# only these ones will be visible / editable. Paths are relative to app.py.
SCHEMA = {
    'pass_threshold': {
        'type': 'numerical',
        'min': 0.1,
        'max': 1.0,
        'default_value': 0.85,
    },

    'custom_timeout': {
        'type': 'numerical',
        'min': 0.0,
        'default_value': 1.5,
    },
    'custom_max_limit': {
        'type': 'numerical',
        'min': 0.0,
        'default_value': 50000,
    },

    'app_name_short': {
        'type': 'string',
        'default_value': "Upmark",
    },
    'app_name_long': {
        'type': 'string',
        'default_value': "Upmark Survey Platform",
    },
    'app_base_url': {
        'type': 'string',
        'default_value': "https://upmark.example",
    },
    'app_redirect': {
        'type': 'boolean',
        'default_value': False,
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
    'theme_nav_bg': {
        'type': 'color',
        'default_value': "#98d5f7",
    },
    'theme_header_bg': {
        'type': 'color',
        'default_value': "#fafafa",
    },
    'theme_sub_header_bg': {
        'type': 'color',
        'default_value': "#fafafa",
    },

    'is_training': {
        'type': 'boolean',
        'default_value': False,
    },
}


def is_primitive(schema):
    return schema['type'] in {'numerical', 'string', 'boolean', 'color'}


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

    elif schema['type'] == 'color':
        if not theme.Color.COLOR_PATTERN.match(value):
            raise ValueError("Setting %s must be a color hex triplet")

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


cache = ExpiringDict(max_len=100, max_age_seconds=10)


def get_resource(name, context=None):
    '''
    @param name - the name of the resource to load, without the file extension.
    '''
    if (name, context) in cache:
        return cache[(name, context)]

    if name in cache:
        config = cache[name]
    else:
        directory = get_package_dir()
        conf_path_stem = '%s/%s' % (directory, name)
        extensions = ('yml', 'yaml', 'json')
        for ext in extensions:
            conf_path = '%s.%s' % (conf_path_stem, ext)
            try:
                with open(conf_path) as f:
                    config = yaml.load(f)
                    break
            except FileNotFoundError:
                continue
        else:
            raise FileNotFoundError(
                "No resource like %s.{%s}" %
                (conf_path_stem, ','.join(extensions)))
        cache[name] = config

    if context is not None:
        config = [
            d for d in config
            if d.get('context', context) == context]

    cache[(name, context)] = config
    return config


def deep_interpolate(config, params):
    if isinstance(config, str):
        return config.format(**params)

    elif hasattr(config, 'items'):
        out_config = {}
        for k, v in config.items():
            try:
                out_config[k] = deep_interpolate(v, params)
            except KeyError as e:
                raise InterpolationError(k, e)
            except InterpolationError as e:
                raise e.prefix(k)
        return out_config

    elif hasattr(config, '__getitem__'):
        out_config = []
        for i, v in enumerate(config):
            try:
                out_config.append(deep_interpolate(v, params))
            except KeyError as e:
                raise InterpolationError(i, e)
            except InterpolationError as e:
                raise e.prefix(i)
        return out_config

    else:
        return config


class InterpolationError(Exception):
    def __init__(self, k, e):
        self.path = [k]
        self.cause = e

    def prefix(self, k):
        e = InterpolationError(k, self.cause)
        e.path.extend(self.path)
        return e

    def __str__(self):
        return "[%s]: %s" % (
            ']['.join(str(k) for k in self.path), self.cause)


def bower_versions():
    if '_bower_versions' in cache:
        return cache['_bower_versions']

    directory = os.path.join(
        get_package_dir(), '..', 'client', 'bower_components')
    versions = {}
    for path in Path(directory).glob('*/.bower.json'):
        with path.open() as f:
            component_meta = yaml.load(f)
        if 'version' in component_meta:
            name = component_meta['name']
            name = name.replace('-', '_')
            versions[name] = component_meta['version']

    cache['_bower_versions'] = versions
    return versions
