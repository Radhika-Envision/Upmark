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


class ProcessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, process_id):
        '''
        Get a single process.
        '''
        if process_id == "":
            function_id = self.get_argument('functionId', None)
            if function_id == None:
                raise handlers.MethodError("Can't GET process without function id.")

            self.query(function_id)
            return

        survey_id = self.check_survey_id()
        
        with model.session_scope() as session:
            try:
                if survey_id == str(get_current_survey()):
                    process = session.query(model.Process).filter_by(id = process_id, survey_id = survey_id).one()
                else:
                    ProcessHistory = model.Process.__history_mapper__.class_
                    process = session.query(ProcessHistory).filter_by(id = process_id, survey_id = survey_id).one()

                if process is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such process")

            son = to_dict(process, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, function_id):
        '''
        Get a list of processs.
        '''
        survey_id = self.check_survey_id()

        sons = []
        with model.session_scope() as session:
            if survey_id == str(get_current_survey()):
                query = session.query(model.Process).filter_by(function_id = function_id, survey_id = survey_id).order_by(model.Process.seq)
            else:
                ProcessHistory = model.Process.__history_mapper__.class_
                query = session.query(ProcessHistory).filter_by(function_id = function_id, survey_id = survey_id).order_by(ProcessHistory.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Process.title.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq', 'description'})
                son = simplify(son)
                son = normalise(son)
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

        survey_id = self.check_survey_id()

        function_id = self.get_argument('functionId', None)
        if function_id == None:
            raise handlers.MethodError("Can't use POST process without function id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                process = model.Process()
                self._update(process, son)
                process.function_id = function_id
                process.survey_id = survey_id
                session.add(process)
                session.flush()
                session.expunge(process)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.finish(str(process.id))

    @handlers.authz('author')
    def put(self, process_id):
        '''
        Update an existing process.
        '''
        if process_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new process (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                process = session.query(model.Process).get(process_id)
                if process is None:
                    raise ValueError("No such object")
                self._update(process, son)
                session.add(process)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such process")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(process_id)

    def check_survey_id(self):
        survey_id = self.get_argument('surveyId', None)
        if survey_id == None:
            raise handlers.MethodError("Can't GET function without survey id.")
        return survey_id

    def _update(self, process, son):
        '''
        Apply process-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            process.title = son['title']
        if son.get('seq', '') != '':
            process.seq = son['seq']
        if son.get('description', '') != '':
            process.description = son['description']
        if son.get('function_id', '') != '':
            process.function_id = son['function_id']
