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

class MeasureHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, measure_id):
        '''
        Get a single measure.
        '''
        if measure_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                measure = session.query(model.Measure).get(measure_id)
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such measure")

            '''
            if user.id != self.current_user.id:
                son = to_dict(user, exclude={'email', 'password'})
            else:
                son = to_dict(user, exclude={'password'})
            son = simplify(son)
            son = normalise(son)
            son["organisation"] = org
            '''
            son = {}
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''
        Get a list of users.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Measure)
            query = query.order_by(model.Measure.seq)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'intent', 'inputs', 'scenario', 'questions'})
                son = simplify(son)
                son = normalise(son)
                # son["category"] = org
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def post(self, measure_id):
        '''
        Create a new user.
        '''
        if measure_id != '':
            raise handlers.MethodError("Can't use POST for existing measure.")

        son = json_decode(self.request.body)
        self._check_create(son)

        try:
            with model.session_scope() as session:
                measure = model.Measure()
                self._check_update(son, None)
                self._update(user, son)
                session.add(measure)
                session.flush()
                session.expunge(measure)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure.id)

    def put(self, measure_id):
        '''
        Update an existing user.
        '''
        if measure_id == '':
            raise handlers.MethodError("Can't use PUT for new measure (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure).get(measure_id)
                if measure is None:
                    raise ValueError("No such object")
                self._check_update(son, measure)
                self._update(measure, son)
                session.add(measure)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such user")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

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
