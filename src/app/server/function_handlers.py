import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

from utils import to_dict, simplify, normalise, get_current_survey,\
        is_current_survey, get_model

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

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        with model.session_scope() as session:
            try:
                functionModel = get_model(is_current, model.Function)
                function = session.query(functionModel)\
                    .filter_by(survey_id = survey_id, id = function_id).one()

                if function is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such function")

            surveyModel = get_model(is_current, model.Survey)
            survey = session.query(surveyModel)\
                .filter_by(id = function.survey_id).one()
            
            survey_json = to_dict(survey, include={'id', 'title'})
            survey_json = simplify(survey_json)
            survey_json = normalise(survey_json)

            son = to_dict(function, include={
                'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
            son['survey'] = survey_json
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list of functions.
        '''

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        sons = []
        with model.session_scope() as session:
            query = None
            functionModel = get_model(is_current, model.Function)
            query = session.query(functionModel)\
                .filter_by(survey_id=survey_id).order_by(functionModel.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    functionModel.title.ilike(r'%{}%'.format(term)))

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
            raise handlers.MethodError(
                "Can't use PUT for new function (no ID).")

        survey_id = self.get_survey_id()
        if survey_id != str(get_current_survey()):
            raise handlers.MethodError("This surveyId is not current one.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                function = model.Function()
                self._update(function, son)
                function.survey_id = survey_id
                session.add(function)
                survey.functions.append(function)
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
            self.ordering()
            return

        survey_id = self.get_survey_id()
        if not is_current_survey(survey_id):
            raise handlers.MethodError("This surveyId is not current one.")

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

    def ordering(self):
        '''
        Update an existing function.
        '''
        survey_id = self.get_survey_id()
        if survey_id != str(get_current_survey()):
            raise handlers.MethodError(
                "This surveyId is not current one.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                functions = session.query(model.Function)\
                    .filter_by(survey_id=survey_id).all()
                functionset = {str(f.id) for f in functions}
                request_order_list = [f["id"] for f in son]

                if functionset != set(request_order_list):
                    raise handlers.MethodError(
                        "List of functions are not matching on server")
                
                request_body_set = dict([ (f["id"], f["seq"]) for f in son ])
                for function in functions:
                    if function.seq != request_body_set[str(function.id)]:
                        raise handlers.MethodError(
                            "Current order is not matching")
                    function.seq = request_order_list.index(str(function.id))
                    session.add(function)
                session.flush()

        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such function")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()


    def get_survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required.")

        return survey_id

    def _update(self, function, son):
        '''
        Apply function-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            function.title = son['title']
        if son.get('description', '') != '':
            function.description = son['description']
