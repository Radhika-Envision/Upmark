from concurrent.futures import ThreadPoolExecutor
import logging
import os

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode, json_encode
import tornado.web
from scour import scour
import sqlalchemy

import handlers
import model
import logo

from utils import get_package_dir, to_camel_case, to_snake_case, ToSon


log = logging.getLogger('app.crud.config')
MAX_WORKERS = 4


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
    'app_name': {
        'type': 'string',
        'default_value': "Upmark",
    },
    'logo': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/logo.svg",
    },
    'logo_monogram_big': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/logo-icon-big.svg",
    },
    'logo_monogram_small': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/logo-icon-small.svg",
    },
}


def is_primitive(schema):
    return schema['type'] in {'numerical', 'string'}


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
            else:
                return setting.value
        if setting.data is not None:
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
            raise handlers.ModelError(
                "Setting %s must be at least %s" % (name, minimum))

        maximum = schema.get('max', float('inf'))
        if maximum < float(value):
            raise handlers.ModelError(
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


class SystemConfigHandler(handlers.BaseHandler):
    @handlers.authz('admin')
    def get(self):
        with model.session_scope() as session:
            settings = {}
            for name, schema in SCHEMA.items():
                if is_private(name, schema):
                    continue

                s = schema.copy()
                s['name'] = to_camel_case(name)
                if 'default_file_path' in s:
                    del s['default_file_path']

                if schema['type'] == 'numerical':
                    s['value'] = float(get_setting(session, name))
                elif schema['type'] == 'string':
                    s['value'] = get_setting(session, name)
                settings[name] = s
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(ToSon()(settings)))
        self.finish()

    @handlers.authz('admin')
    def put(self):
        with model.session_scope() as session:
            settings = {}
            for name, schema in SCHEMA.items():
                if is_private(name, schema):
                    continue

                if name not in self.request_son:
                    reset_setting(session, name)
                    continue

                if is_primitive(schema):
                    set_setting(session, name, self.request_son[name]['value'])
        self.get()


class SystemConfigItemHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, name):
        self.check_privillege('admin')
        name = to_snake_case(name)
        schema = SCHEMA.get(name)
        if not schema or is_private(name, schema):
            raise handlers.MissingDocError("No such setting")
        if is_primitive(schema):
            raise handlers.MissingDocError(
                "This service can only be used to get blob data, not text or "
                "numerical values.")

        if schema['type'] == 'image' and schema['accept'] == '.svg':
            self.set_header('Content-Type', 'image/svg+xml')
        else:
            self.clear_header('Content-Type')

        with model.session_scope() as session:
            value = get_setting(
                session, name,
                force_default=self.get_argument('default', None) != None)
            self.write(value)

        self.finish()

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, name):
        self.check_privillege('admin')
        name = to_snake_case(name)
        schema = SCHEMA.get(name)
        if not schema or is_private(name, schema):
            raise handlers.MissingDocError("No such setting")
        if is_primitive(schema):
            raise handlers.MissingDocError(
                "This service can only be used to set blob data, not text or "
                "numerical values.")

        fileinfo = self.request.files['file'][0]
        body = fileinfo['body']
        if schema['type'] == 'image' and schema['accept'] == '.svg':
            body = yield self.clean_svg(body)

        with model.session_scope() as session:
            set_setting(session, name, body.encode('utf-8'))

        self.finish()

    @tornado.web.authenticated
    def delete(self, name):
        self.check_privillege('admin')
        name = to_snake_case(name)
        schema = SCHEMA.get(name)
        if not schema or is_private(name, schema):
            raise handlers.MissingDocError("No such setting")
        with model.session_scope() as session:
            reset_setting(session, name)

        self.finish()

    @run_on_executor
    def clean_svg(self, svg):
        return logo.clean_svg(svg)
