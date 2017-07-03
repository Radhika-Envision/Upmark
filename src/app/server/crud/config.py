from concurrent.futures import ThreadPoolExecutor
import logging

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_encode
import tornado.web

import base_handler
import config
import errors
import model
import image

from utils import to_camel_case, to_snake_case, ToSon


log = logging.getLogger('app.crud.config')
MAX_WORKERS = 4


class SystemConfigHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        self.authz_policy.verify('conf_view')
        with model.session_scope() as session:
            settings = {}
            for name, schema in config.SCHEMA.items():
                if config.is_private(name, schema):
                    continue

                s = schema.copy()
                s['name'] = to_camel_case(name)
                if 'default_file_path' in s:
                    del s['default_file_path']

                s['value'] = config.get_setting(session, name)
                settings[name] = s
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(ToSon()(settings)))
        self.finish()

    @tornado.web.authenticated
    def put(self):
        self.authz_policy.verify('conf_edit')
        with model.session_scope() as session:
            for name, schema in config.SCHEMA.items():
                if config.is_private(name, schema):
                    continue

                if name not in self.request_son:
                    config.reset_setting(session, name)
                    continue

                if config.is_primitive(schema):
                    config.set_setting(
                        session, name, self.request_son[name]['value'])
        self.get()


class SystemConfigItemHandler(base_handler.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, name):
        self.authz_policy.verify('conf_view')
        name = to_snake_case(name)
        schema = config.SCHEMA.get(name)
        if not schema or config.is_private(name, schema):
            raise errors.MissingDocError("No such setting")
        if config.is_primitive(schema):
            raise errors.MissingDocError(
                "This service can only be used to get blob data, not text or "
                "numerical values.")

        if schema['type'] == 'image' and schema['accept'] == '.svg':
            self.set_header('Content-Type', 'image/svg+xml')
        else:
            self.clear_header('Content-Type')

        with model.session_scope() as session:
            value = config.get_setting(
                session, name,
                force_default=self.get_argument('default', None) != None)
            self.write(value)

        self.finish()

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, name):
        self.authz_policy.verify('conf_edit')
        name = to_snake_case(name)
        schema = config.SCHEMA.get(name)
        if not schema or config.is_private(name, schema):
            raise errors.MissingDocError("No such setting")
        if config.is_primitive(schema):
            raise errors.MissingDocError(
                "This service can only be used to set blob data, not text or "
                "numerical values.")

        fileinfo = self.request.files['file'][0]
        body = fileinfo['body']
        if schema['type'] == 'image' and schema['accept'] == '.svg':
            body = yield self.clean_svg(body)

        with model.session_scope() as session:
            config.set_setting(session, name, body.encode('utf-8'))

        self.finish()

    @tornado.web.authenticated
    def delete(self, name):
        self.authz_policy.verify('conf_del')
        name = to_snake_case(name)
        schema = config.SCHEMA.get(name)
        if not schema or config.is_private(name, schema):
            raise errors.MissingDocError("No such setting")
        with model.session_scope() as session:
            config.reset_setting(session, name)

        self.finish()

    @run_on_executor
    def clean_svg(self, svg):
        return image.clean_svg(svg)
