import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

log = logging.getLogger('app.data_access')

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


def normalise(ob_dict):
    new_dict = {}
    for name, value in ob_dict.items():
        components = name.split('_')
        if len(components) > 1 and components[-1] == 'id':
            components = components[:-1]
        components = [components[0]] + [c.title() for c in components[1:]]
        name = ''.join(components)
        new_dict[name] = value
    return new_dict


class OrgHandler(handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, org_id):
        if org_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such organisation")
            son = to_dict(org)
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        term = self.get_argument('term', None)
        if term:
            self.search(term)
            return

        sons = []
        with model.session_scope() as session:
            obs = session.query(model.Organisation).all()
            for ob in obs:
                son = to_dict(ob, include={'id', 'name'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def search(self, term):
        sons = []
        with model.session_scope() as session:
            obs = session.query(model.Organisation).filter(model.Organisation.name.ilike('%'+term+'%')).all()
            for ob in obs:
                son = to_dict(ob, include={'id', 'name'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()


class UserHandler(handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, user_id):
        '''
        Get a single user.
        '''
        if user_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                user = session.query(model.AppUser).get(user_id)
                if user is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such user")
            if user.id != self.current_user.id:
                son = to_dict(user, exclude={'email', 'password'})
            else:
                son = to_dict(user, exclude={'password'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''
        Get a list of users.
        '''
        sons = []
        with model.session_scope() as session:
            obs = session.query(model.AppUser).options(joinedload('organisation')).all()
            for ob in obs:
                org = to_dict(ob.organisation, include={'id', 'name'})
                org = simplify(org)
                org = normalise(org)
                son = to_dict(ob, include={'id', 'name', 'email'})
                son = simplify(son)
                son = normalise(son)
                son["organisation"] = org
                sons.append(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('admin', 'org_admin')
    def post(self, user_id):
        '''
        Create a new user.
        '''
        if user_id != '':
            raise handlers.MethodError("Can't use POST for existing users.")
        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                user = model.AppUser()
                self._update(user, son)
                session.add(user)
                session.flush()
                session.expunge(user)
        except sqlalchemy.exc.IntegrityError:
            raise handlers.ModelError("Arguments are invalid")
        self.get(user.id)

    def put(self, user_id):
        '''
        Update an existing user.
        '''
        if user_id == '':
            raise handlers.MethodError("Can't use PUT for new users (no ID).")
        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                user = session.query(model.AppUser).get(user_id)
                if user is None:
                    raise ValueError("No such object")
                self._update(user, son)
                session.add(user)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such user")
        except sqlalchemy.exc.IntegrityError:
            raise handlers.ModelError("Arguments are invalid")
        self.get(user_id)

    def _update(self, user, son):
        '''
        Apply user-provided data to the saved model.
        '''
        if son.get('email', '') != '':
            user.email = son['email']
        if son.get('name', '') != '':
            user.name = son['name']
        if son.get('role', '') != '':
            user.role = son['role']
        if son.get('organisation_id', '') != '':
            user.role = son['organisation_id']
        if son.get('password', '') != '':
            user.set_password(son['password'])
