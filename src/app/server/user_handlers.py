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

from utils import to_dict, simplify, normalise

class UserHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, user_id):
        '''
        Get a single user.
        '''
        if user_id == "":
            self.query()
            return

        if user_id == 'current':
            user_id = str(self.current_user.id)

        with model.session_scope() as session:
            try:
                user = session.query(model.AppUser).options(joinedload('organisation')).get(user_id)
                if user is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such user")
            org = to_dict(user.organisation, include={'id', 'name'})
            org = simplify(org)
            org = normalise(org)

            if not self._can_see_email(user):
                son = to_dict(user, exclude={'email', 'password'})
            else:
                son = to_dict(user, exclude={'password'})
            son = simplify(son)
            son = normalise(son)
            son["organisation"] = org
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def _can_see_email(self, user):
        if model.has_privillege(self.current_user.role, 'admin'):
            return True
        elif user.id == self.current_user.id:
            return True
        elif model.has_privillege(self.current_user.role, 'org_admin'):
            return self.current_user.organisation_id == user.organisation_id
        else:
            return False

    def query(self):
        '''
        Get a list of users.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.AppUser)\
                .options(joinedload('organisation'))

            org_id = self.get_argument("org_id", None)
            if org_id is not None:
                query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.AppUser.name.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.AppUser.name)
            query = self.paginate(query)

            for ob in query.all():
                org = to_dict(ob.organisation, include={'id', 'name'})
                org = simplify(org)
                org = normalise(org)
                son = to_dict(ob, include={'id', 'name'})
                son = simplify(son)
                son = normalise(son)
                son["organisation"] = org
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def post(self, user_id):
        '''
        Create a new user.
        '''
        if user_id != '':
            raise handlers.MethodError("Can't use POST for existing users.")

        son = json_decode(self.request.body)
        self._check_create(son)

        try:
            with model.session_scope() as session:
                user = model.AppUser()
                user.organisation_id = son['organisation']['id'];
                self._check_update(son, None)
                self._update(user, son)
                session.add(user)
                session.flush()
                session.expunge(user)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
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
                self._check_update(son, user)
                self._update(user, son)
                session.add(user)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such user")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(user_id)

    def _check_create(self, son):
        if not model.has_privillege(self.current_user.role, 'org_admin'):
            raise handlers.MethodError("You can't create a new user.")

    def _check_update(self, son, user):
        if model.has_privillege(self.current_user.role, 'admin'):
            pass
        elif model.has_privillege(self.current_user.role, 'org_admin'):
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't create/modify another organisation's user.")
            if son['role'] not in {'org_admin', 'clerk'}:
                raise handlers.MethodError(
                    "You can't set this role.")
            if user and user.role == 'admin':
                raise handlers.MethodError(
                    "You can't modify a user with that role.")
        else:
            if str(self.current_user.id) != user.id:
                raise handlers.MethodError(
                    "You can't modify another user.")
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't change your organisation.")
            if son['role'] != self.current_user.role:
                raise handlers.MethodError(
                    "You can't change your role.")

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
        if son.get('organisation', '') != '':
            user.organisation_id = son['organisation']['id']
        if son.get('password', '') != '':
            user.set_password(son['password'])
