from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy

import handlers
import model
import logging

from utils import ToSon


# This SCHEMA defines configuration parameters that a user is allowed to modify.
# The application may store other things in the systemconfig table, but only
# these ones will be visible / editable.
SCHEMA = [
    {
        'name': 'pass_threshold',
        'human_name': "Password Strength Threshold",
        'description':
            "The minimum strength for a password, between 0.0 and 1.0, where"
            " 0.0 allows very weak passwords and 1.0 requires strong"
            " passwords.",
        'default_value': "0.85"
    }, {
        'name': 'adhoc_timeout',
        'human_name': "Custom Query Time Limit",
        'description':
            "The maximum number of seconds a custom query is allowed to run"
            " for.",
        'default_value': "1.5"
    }, {
        'name': 'adhoc_max_limit',
        'human_name': "Custom Query Row Limit",
        'description':
            "The maximum number of rows a query can return.",
        'default_value': "2500"
    }, {
        'name': 'logo',
        'human_name': "Application logo",
        'description':
            "The primary logo used for the application.",
        'default_file_path': "../../client/images/logo.svg"
    }, {
        'name': 'logo_monogram_big',
        'human_name': "Large square icon",
        'description':
            "A large square icon to use as app launcher.",
        'default_file_path': "../../client/images/logo-icon-big.svg"
    }, {
        'name': 'logo_monogram_small',
        'human_name': "Small square icon",
        'description':
            "A small square icon to display in browser tabs.",
        'default_file_path': "../../client/images/logo-icon-small.svg"
    }
]


class SystemConfigHandler(handlers.BaseHandler):

    @handlers.authz('admin')
    def get(self):
        with model.session_scope() as session:
            try:
                settings = session.query(model.SystemConfig) \
                    .filter(model.SystemConfig.user_defined == True) \
                    .all()
            except sqlalchemy.exc.StatementError:
                raise handlers.MissingDocError("No such user")
            to_son = ToSon()
            to_son.exclude(r'/user_defined$')
            son = {
                'id': 'settings',
                'settings': to_son(settings)
            }
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @handlers.authz('admin')
    def put(self):
        try:
            with model.session_scope() as session:
                for s in self.request_son['settings']:
                    setting = session.query(model.SystemConfig).get(s['name'])
                    if setting is None:
                        raise handlers.MissingDocError(
                            "No such setting %s" % s['name'])
                    if not setting.user_defined:
                        raise handlers.ModelError(
                            "Setting %s can't be modified" % s['name'])
                    setting.value = s['value']
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        except sqlalchemy.exc.StatementError:
            raise handlers.MissingDocError("No such setting")
        self.get()
