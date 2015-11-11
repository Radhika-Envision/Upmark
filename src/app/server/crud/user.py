import datetime
import time
import uuid

import passwordmeter
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

from utils import ToSon, truthy, updater


def test_password(text):
    with model.session_scope() as session:
        setting = session.query(model.SystemConfig).get('pass_threshold')
        threshold = float(setting.value)
    password_tester = passwordmeter.Meter(settings={
            'threshold': threshold,
            'pessimism': 10,
            'factor.casemix.weight': 0.3})
    strength, improvements = password_tester.test(text)
    return strength, threshold, improvements


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
                user = session.query(model.AppUser).\
                    options(joinedload('organisation')).get(user_id)
                if user is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such user")

            to_son = ToSon(include=[
                r'/id$',
                r'/name$',
                r'/email$',
                r'/role$',
                r'/enabled$',
                # Descend into nested objects
                r'/organisation$',
            ], exclude=[
                # Exclude password from response. Not really necessary because
                # 1. it's hashed and 2. it's not in the list above. But just to
                # be safe.
                r'password'
            ])
            son = to_son(user)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

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

            enabled = self.get_argument('enabled', None)
            if enabled is not None:
                enable = truthy(enabled)
                query = query.filter(model.AppUser.enabled == enabled)

            query = query.order_by(model.AppUser.name)
            query = self.paginate(query)

            to_son = ToSon(include=[
                r'/id$',
                r'/name$',
                r'/enabled$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/organisation$',
            ], exclude=[
                # Exclude password from response. Not really necessary because
                # 1. it's hashed and 2. it's not in the list above. But just to
                # be safe.
                r'password'
            ])

            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, user_id):
        '''
        Create a new user.
        '''
        if user_id != '':
            raise handlers.MethodError("Can't use POST for existing users.")

        self._check_create(self.request_son)

        try:
            with model.session_scope() as session:
                user = model.AppUser()
                user.organisation_id = self.request_son['organisation']['id']
                self._check_update(self.request_son, None)
                self._update(user, self.request_son)
                session.add(user)
                session.flush()
                session.expunge(user)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(user.id)

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Update an existing user.
        '''
        if user_id == '':
            raise handlers.MethodError("Can't use PUT for new users (no ID).")

        try:
            with model.session_scope() as session:
                user = session.query(model.AppUser).get(user_id)
                if user is None:
                    raise ValueError("No such object")
                self._check_update(self.request_son, user)
                self._update(user, self.request_son)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such user")
        self.get(user_id)

    @tornado.web.authenticated
    def delete(self, user_id):
        if user_id == '':
            raise handlers.MethodError("User ID required")
        try:
            with model.session_scope() as session:
                user = session.query(model.AppUser).get(user_id)
                if user is None:
                    raise ValueError("No such object")
                self._check_delete(user)
                user.organisation.users.remove(user)
                session.delete(user)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError(
                "User owns content and can not be deleted")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such user")

        self.finish()

    def _check_create(self, son):
        if not model.has_privillege(self.current_user.role, 'org_admin'):
            raise handlers.AuthzError("You can't create a new user.")

    def _check_update(self, son, user):
        if model.has_privillege(self.current_user.role, 'admin'):
            pass
        elif model.has_privillege(self.current_user.role, 'org_admin'):
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.AuthzError(
                    "You can't create/modify another organisation's user.")
            if son['role'] not in {'org_admin', 'clerk'}:
                raise handlers.AuthzError(
                    "You can't set this role.")
            if user and user.role == 'admin':
                raise handlers.AuthzError(
                    "You can't modify a user with that role.")
        else:
            if str(self.current_user.id) != str(user.id):
                raise handlers.AuthzError(
                    "You can't modify another user.")
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.AuthzError(
                    "You can't change your organisation.")
            if son['role'] != self.current_user.role:
                raise handlers.AuthzError(
                    "You can't change your role.")

        if 'enabled' in son and son['enabled'] != user.enabled:
            if str(self.current_user.id) == str(user.id):
                raise handlers.AuthzError(
                    "You can't enable or disable yourself.")

        if son.get('password', '') != '':
            strength, threshold, _ = test_password(son['password'])
            if strength < threshold:
                raise handlers.ModelError("Password is not strong enough")

    def _check_delete(self, user):
        if str(self.current_user.id) == str(user.id):
            raise handlers.AuthzError(
                "You can't delete yourself.")

        if model.has_privillege(self.current_user.role, 'admin'):
            pass
        elif model.has_privillege(self.current_user.role, 'org_admin'):
            if str(self.organisation.id) != str(user.organisation_id):
                raise handlers.AuthzError(
                    "You can't delete another organisation's user.")
        elif str(self.current_user.id) != str(user.id):
            raise handlers.AuthzError(
                "You can't delete another user.")

    def _update(self, user, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(user)
        update('email', son)
        update('name', son)
        update('role', son)
        update('enabled', son)

        if son.get('organisation', '') != '':
            user.organisation_id = son['organisation']['id']
        if son.get('password', '') != '':
            user.set_password(son['password'])


class PasswordHandler(handlers.BaseHandler):

    def post(self):
        '''
        Check the strength of a password.
        '''

        if 'password' not in self.request_son:
            raise handlers.ModelError("Please specify a password")

        strength, threshold, improvements = test_password(
            self.request_son['password'])
        son = {
            'threshold': threshold,
            'strength': strength,
            'improvements': improvements
        }

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()
