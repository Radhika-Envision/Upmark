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

class SurveyHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, survey_id):
        '''
        Get a single survey.
        '''
        if survey_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such survey")

            '''
            if survey.id != self.current_survey.id:
                son = to_dict(survey, exclude={'email', 'password'})
            else:
                son = to_dict(survey, exclude={'password'})
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
        Get a list of surveys.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Survey)

            # org_id = self.get_argument("org_id", None)
            # if org_id is not None:
            #     query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Survey.name.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Survey.name)
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

    def post(self, survey_id):
        '''
        Create a new survey.
        '''
        if survey_id != '':
            raise handlers.MethodError("Can't use POST for existing survey.")

        son = json_decode(self.request.body)
        self._check_create(son)

        try:
            with model.session_scope() as session:
                survey = model.Survey()
                self._check_update(son, None)
                self._update(survey, son)
                session.add(survey)
                session.flush()
                session.expunge(survey)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey.id)

    def put(self, survey_id):
        '''
        Update an existing survey.
        '''
        if survey_id == '':
            raise handlers.MethodError("Can't use PUT for new surveys (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
                self._check_update(son, survey)
                self._update(survey, son)
                session.add(survey)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def _check_create(self, son):
        if not model.has_privillege(self.current_survey.role, 'org_admin'):
            raise handlers.MethodError("You can't create a new survey.")

    def _check_update(self, son, survey):
        if model.has_privillege(self.current_survey.role, 'admin'):
            pass
        elif model.has_privillege(self.current_survey.role, 'org_admin'):
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't create/modify another organisation's survey.")
            if son['role'] not in {'org_admin', 'clerk'}:
                raise handlers.MethodError(
                    "You can't set this role.")
            if survey and survey.role == 'admin':
                raise handlers.MethodError(
                    "You can't modify a survey with that role.")
        else:
            if str(self.current_survey.id) != survey.id:
                raise handlers.MethodError(
                    "You can't modify another survey.")
            if str(self.organisation.id) != son['organisation']['id']:
                raise handlers.MethodError(
                    "You can't change your organisation.")
            if son['role'] != self.current_survey.role:
                raise handlers.MethodError(
                    "You can't change your role.")

    def _update(self, survey, son):
        '''
        Apply survey-provided data to the saved model.
        '''
        if son.get('email', '') != '':
            survey.email = son['email']
        if son.get('name', '') != '':
            survey.name = son['name']
        if son.get('role', '') != '':
            survey.role = son['role']
        if son.get('organisation', '') != '':
            survey.organisation_id = son['organisation']['id']
        if son.get('password', '') != '':
            survey.set_password(son['password'])
