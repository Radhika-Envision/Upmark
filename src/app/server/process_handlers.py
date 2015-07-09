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

from utils import to_dict, simplify, normalise, get_current_survey, is_current_survey, get_model

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
                raise handlers.MethodError("Can't GET process without function id.")

            self.query(function_id)
            return

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)
        
        with model.session_scope() as session:
            try:
                processModel = get_model(is_current, model.Process)
                process = session.query(processModel).filter_by(id = process_id, survey_id = survey_id).one()

                if process is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such process")

            functionModel = get_model(is_current, model.Function)
            surveyModel = get_model(is_current, model.Survey)
            function = session.query(functionModel).filter_by(id = process.function_id, survey_id = survey_id).one()
            survey = session.query(surveyModel).filter_by(id = survey_id).one()
            
            survey_json = to_dict(survey, include={'id', 'title'})
            survey_json = simplify(survey_json)
            survey_json = normalise(survey_json)

            function_json = to_dict(function, include={'id', 'title', 'seq', 'description'})
            function_json = simplify(function_json)
            function_json = normalise(function_json)
            function_json['survey'] = survey_json

            son = to_dict(process, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
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
            processModel = get_model(is_current, model.Process)
            query = session.query(processModel).filter_by(function_id = function_id, survey_id = survey_id).order_by(processModel.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    processModel.title.ilike(r'%{}%'.format(term)))

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

        survey_id = self.get_survey_id()
        function_id = self.get_argument("functionId", "")
        if function_id == None:
            raise handlers.MethodError("Can't use POST process without function id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                # This is OK because POST is always for the current survey
                function = session.query(model.Function).get(function_id)
                process = model.Process()
                self._update(process, son)
                process.function_id = function_id
                process.survey_id = survey_id
                function.processes.append(process)
                session.add(process)
                session.flush()
                session.expunge(process)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(process.id)

    @handlers.authz('author')
    def put(self, process_id):
        '''
        Update an existing process.
        '''
        if process_id == '':
            self.ordering()
            return

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

    def ordering(self):
        '''
        Update an existing function.
        '''
        survey_id = self.get_survey_id()
        if not is_current_survey(survey_id):
            raise handlers.MethodError("This surveyId is not current one.")

        function_id = self.get_argument("functionId", "")
        if function_id == None:
            raise handlers.MethodError("Can't GET process without function id.")



        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                processes = session.query(model.Process).filter_by(survey_id=survey_id, function_id=function_id).all()
                processset = {str(f.id) for f in processes}
                request_order_list = [f["id"] for f in son]

                if processset != set(request_order_list):
                    raise handlers.MethodError("List of functions are not matching on server")
                
                request_body_set = dict([ (f["id"], f["seq"]) for f in son ])
                for process in processes:
                    if process.seq != request_body_set[str(process.id)]:
                        raise handlers.MethodError("Current order is not matching")
                    process.seq = request_order_list.index(str(process.id))
                    session.add(process)
                session.flush()

        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such function")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query(function_id)

    def get_survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Can't get function without survey id.")

        return survey_id

    def _update(self, process, son):
        '''
        Apply process-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            process.title = son['title']
        if son.get('description', '') != '':
            process.description = son['description']
