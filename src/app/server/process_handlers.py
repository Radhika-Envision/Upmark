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

from utils import to_dict, get_current_survey, is_current_survey, reorder

log = logging.getLogger('app.data_access')


class ProcessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, process_id):
        '''
        Get a single process.
        '''
        if process_id == "":
            function_id = self.get_argument("functionId", "")
            if function_id == None:
                raise handlers.MethodError(
                    "Function ID is required.")

            self.query(function_id)
            return

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)
        
        with model.session_scope() as session:
            try:
                process = session.query(model.Process)\
                    .filter_by(id=process_id, survey_id=survey_id).one()

                if process is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such process")

            function = process.function
            survey = function.survey

            survey_json = to_dict(survey, include={'id', 'title'})
            function_json = to_dict(function, include={'id', 'title', 'seq'})
            function_json['survey'] = survey_json

            son = to_dict(process, include={
                'id', 'title', 'seq', 'description'})
            son['function'] = function_json
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, function_id):
        '''
        Get a list of processs.
        '''
        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Process)\
                .filter_by(function_id=function_id, survey_id=survey_id)\
                .order_by(model.Process.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Process.title.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq', 'description'})
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, process_id):
        '''
        Create a new process.
        '''
        if process_id != '':
            raise handlers.MethodError("Can't use POST for existing process.")

        survey_id = self.get_survey_id()
        function_id = self.get_argument("functionId", "")
        if function_id == None:
            raise handlers.MethodError("Can't use POST process without function id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                # This is OK because POST is always for the current survey
                function = session.query(model.Function)\
                    .get((function_id, survey_id))
                process = model.Process()
                self._update(process, son)
                process.function_id = function_id
                process.survey_id = survey_id
                function.processes.append(process)
                session.flush()
                session.expunge(process)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(process.id)

    @handlers.authz('author')
    def delete(self, process_id):
        '''
        Delete an existing process.
        '''
        if process_id == '':
            raise handlers.MethodError("Process ID required")
        survey_id = self.get_survey_id()
        try:
            with model.session_scope() as session:
                process = session.query(model.Process)\
                    .get((process_id, survey_id))
                if process is None:
                    raise ValueError("No such object")
                session.delete(process)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Process is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such process")

        self.finish()

    @handlers.authz('author')
    def put(self, process_id):
        '''
        Update an existing process.
        '''
        if process_id == '':
            self.ordering()
            return

        son = json_decode(self.request.body)

        survey_id = self.get_survey_id()
        try:
            with model.session_scope() as session:
                process = session.query(model.Process)\
                    .get((process_id, survey_id))
                if process is None:
                    raise ValueError("No such object")
                self._update(process, son)
                session.add(process)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such process")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(process_id)

    def ordering(self):
        '''
        Update an existing function.
        '''
        survey_id = self.get_survey_id()
        if not is_current_survey(survey_id):
            raise handlers.MethodError("This surveyId is not current one.")

        function_id = self.get_argument("functionId", "")
        if function_id == None:
            raise handlers.MethodError("Function ID is required.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                function = session.query(model.Function)\
                    .get((function_id, survey_id))
                reorder(function.processes, son)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query(function_id)

    def get_survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required.")

        return survey_id

    def _update(self, process, son):
        '''
        Apply process-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            process.title = son['title']
        if son.get('description', '') != '':
            process.description = son['description']
