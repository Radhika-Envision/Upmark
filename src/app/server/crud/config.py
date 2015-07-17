from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy

import handlers
import model
import logging

from utils import to_dict, simplify, normalise, truthy


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
            son = {
                'id': 'settings',
                'settings': [to_dict(setting, exclude={'user_defined'})
                             for setting in settings]
            }
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @handlers.authz('admin')
    def put(self):
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                for s in son['settings']:
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
