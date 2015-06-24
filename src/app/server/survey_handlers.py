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
            if measure.id != self.current_measure.id:
                son = to_dict(measure, exclude={'email', 'password'})
            else:
                son = to_dict(measure, exclude={'password'})
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
        Get a list of measures.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Measure)

            # org_id = self.get_argument("org_id", None)
            # if org_id is not None:
            #     query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Measure.name.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Measure.name)
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

    def post(self, measure_id):
        '''
        Create a new measure.
        '''
        if measure_id != '':
            raise handlers.MethodError("Can't use POST for existing measure.")

        son = json_decode(self.request.body)
        self._check_create(son)

        try:
            with model.session_scope() as session:
                measure = model.Measure()
                self._check_update(son, None)
                self._update(measure, son)
                session.add(measure)
                session.flush()
                session.expunge(measure)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure.id)

    def put(self, measure_id):
        '''
        Update an existing measure.
        '''
        if measure_id == '':
            raise handlers.MethodError("Can't use PUT for new measures (no ID).")
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
            raise handlers.MissingDocError("No such measure")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    def _check_create(self, son):
        if not model.has_privillege(self.current_measure.role, 'org_admin'):
            raise handlers.MethodError("You can't create a new measure.")

    def _check_update(self, son, measure):
        if model.has_privillege(self.current_measure.role, 'admin'):
            pass
        elif model.has_privillege(self.current_measure.role, 'org_admin'):
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't create/modify another organisation's measure.")
            if son['role'] not in {'org_admin', 'clerk'}:
                raise handlers.MethodError(
                    "You can't set this role.")
            if measure and measure.role == 'admin':
                raise handlers.MethodError(
                    "You can't modify a measure with that role.")
        else:
            if str(self.current_measure.id) != measure.id:
                raise handlers.MethodError(
                    "You can't modify another measure.")
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't change your organisation.")
            if son['role'] != self.current_measure.role:
                raise handlers.MethodError(
                    "You can't change your role.")

    def _update(self, measure, son):
        '''
        Apply measure-provided data to the saved model.
        '''
        if son.get('email', '') != '':
            measure.email = son['email']
        if son.get('name', '') != '':
            measure.name = son['name']
        if son.get('role', '') != '':
            measure.role = son['role']
        if son.get('organisation', '') != '':
            measure.organisation_id = son['organisation']['id']
        if son.get('password', '') != '':
            measure.set_password(son['password'])
