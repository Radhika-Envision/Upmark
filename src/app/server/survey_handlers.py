import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

from utils import to_dict, simplify, normalise

log = logging.getLogger('app.data_access')


class SurveyHandler(handlers.Paginate, handlers.BaseHandler):

    # @handlers.authz('author')
    def get(self, survey_id):
        '''
        Get a single survey.
        '''
        if survey_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                query = session.query(model.Survey)
                if survey_id == 'current':
                    survey = query.order_by(model.Survey.created.desc()).first()
                else:
                    survey = query.get(survey_id)
                log.info(survey)
                if survey is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such survey")

            son = to_dict(survey, include={'id', 'title', 'branch'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    # @handlers.authz('author')
    def query(self):
        '''
        Get a list of surveys.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Survey)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Survey.title.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Survey.title)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'branch'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
    
    # @handlers.authz('author')
    def post(self, survey_id):
        '''
        Create a new survey.
        '''
        if survey_id != '':
            raise handlers.MethodError("Can't use POST for existing survey.")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                survey = model.Survey()
                self._update(survey, son)
                session.add(survey)
                session.flush()
                session.expunge(survey)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey.id)

    # @handlers.authz('author')
    def put(self, survey_id):
        '''
        Update an existing survey.
        '''
        if survey_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new survey (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
                self._update(survey, son)
                session.add(survey)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def _update(self, survey, son):
        '''
        Apply survey-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            survey.title = son['title']
