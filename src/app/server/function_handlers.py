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

from utils import to_dict, simplify, normalise, get_current_survey

log = logging.getLogger('app.data_access')


class FunctionHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, function_id):
        '''
        Get a single function.
        '''
        if function_id == "":
            self.query()
            return

        survey_id = self.checkSurveyId()

        with model.session_scope() as session:
            if survey_id == str(get_current_survey()):
                function = session.query(model.Function).filter_by(survey_id = survey_id, id = function_id).one()
            else:
                FunctionHistory = model.Function.__history_mapper__.class_
                function = session.query(FunctionHistory).filter_by(id = function_id, survey_id = survey_id).one()

            if function is None:
                raise ValueError("No such object")

            son = to_dict(function, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list of functions.
        '''

        survey_id = self.checkSurveyId()

        sons = []
        with model.session_scope() as session:
            query = None
            if survey_id == str(get_current_survey()):
                query = session.query(model.Function).order_by(model.Function.seq)
            else:
                FunctionHistory = model.Function.__history_mapper__.class_
                query = session.query(FunctionHistory).order_by(FunctionHistory.seq)
                query = query.filter_by(survey_id=survey_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Function.title.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, function_id):
        '''
        Create a new function.
        '''
        if function_id != '':
            raise handlers.MethodError("Can't use POST for existing function.")

        survey_id = self.checkSurveyId()
        if survey_id != str(get_current_survey()):
            raise handlers.MethodError("This surveyId is not current one.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                function = model.Function()
                self._update(function, son)
                function.survey_id = survey_id
                session.add(function)
                session.flush()
                session.expunge(function)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(function.id)

    @handlers.authz('author')
    def put(self, function_id):
        '''
        Update an existing function.
        '''
        if function_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new function (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                function = session.query(model.Function).get(function_id)
                if function is None:
                    raise ValueError("No such object")
                self._update(function, son)
                session.add(function)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such function")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(function_id)

    def checkSurveyId(self):
        survey_id = self.get_argument('surveyId', None)
        if survey_id == None:
            raise handlers.MethodError("Can't GET function without survey id.")
        return survey_id

    def _update(self, function, son):
        '''
        Apply function-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            function.title = son['title']
        if son.get('seq', '') != '':
            function.seq = son['seq']
        if son.get('description', '') != '':
            function.description = son['description']
        if son.get('branch', '') != '':
            function.branch = son['branch']
