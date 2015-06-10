import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy

import handlers
import model


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
    new_dict = {}
    for name, value in ob_dict.items():
        if isinstance(value, datetime.date):
            value = time.mktime(value.timetuple())
        elif isinstance(value, uuid.UUID):
            value = str(value)
        new_dict[name] = value
    return new_dict


class OrgHandler(handlers.BaseHandler):
    def get(self, org_id):
        with model.session_scope() as session:
            try:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such organisation")
            deref_org = simplify(to_dict(org))
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(deref_org))
        self.finish()


class UserHandler(handlers.BaseHandler):
    def get(self, user_id):
        with model.session_scope() as session:
            try:
                user = session.query(model.AppUser).get(user_id)
                if user is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such user")
            if user.id != self.current_user.id:
                exclusion = {'email', 'password'}
            else:
                exclusion = {'password'}
            deref_user = simplify(to_dict(user, exclude=exclusion))
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(deref_user))
        self.finish()
