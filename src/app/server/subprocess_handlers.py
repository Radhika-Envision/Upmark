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

from utils import to_dict, simplify, normalise, get_current_survey,\
        is_current_survey, get_model, reorder

log = logging.getLogger('app.data_access')


class SubprocessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, subprocess_id):
        '''
        Get a single subprocess.
        '''
        if subprocess_id == "":
            process_id = self.get_argument("processId", "")
            if process_id == None:
                raise handlers.MethodError(
                    "Can't GET subprocess without process id.")

            self.query(process_id)
            return

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        with model.session_scope() as session:
            try:
                subprocessModel = get_model(is_current, model.Subprocess)
                subprocess = session.query(subprocessModel)\
                    .filter_by(id = subprocess_id, survey_id=survey_id).one()

                if subprocess is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such subprocess")

            processModel = get_model(is_current, model.Process)
            functionModel = get_model(is_current, model.Function)
            surveyModel = get_model(is_current, model.Survey)

            process = session.query(processModel)\
                .filter_by(id=subprocess.process_id, survey_id=survey_id)\
                .one()
            function = session.query(functionModel)\
                .filter_by(id=process.function_id, survey_id=survey_id)\
                .one()
            survey = session.query(surveyModel).filter_by(id=survey_id).one()
            
            survey_json = to_dict(survey, include={'id', 'title'})
            survey_json = simplify(survey_json)
            survey_json = normalise(survey_json)

            function_json = to_dict(function, include={'id', 'title', 'seq'})
            function_json = simplify(function_json)
            function_json = normalise(function_json)
            function_json['survey'] = survey_json

            process_json = to_dict(process, include={'id', 'title', 'seq'})
            process_json = simplify(process_json)
            process_json = normalise(process_json)
            process_json['function'] = function_json

            son = to_dict(subprocess, include={
                'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
            son['process'] = process_json

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, process_id):
        '''
        Get a list of subprocesss.
        '''
        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        sons = []
        with model.session_scope() as session:
            subprocessModel = get_model(is_current, model.Subprocess)
            query = session.query(subprocessModel)\
                .filter_by(process_id=process_id, survey_id=survey_id)\
                .order_by(subprocessModel.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    subprocessModel.title.ilike(r'%{}%'.format(term)))

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
    def post(self, subprocess_id):
        '''
        Create a new subprocess.
        '''
        if subprocess_id != '':
            raise handlers.MethodError(
                "Can't use POST for existing subprocess.")

        survey_id = self.get_survey_id()

        process_id = self.get_argument("processId", "")
        if process_id == None:
            raise handlers.MethodError("Process ID is required.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                # This is OK because POST is always for the current survey
                process = session.query(model.Process).get(process_id)
                subprocess = model.Subprocess()
                self._update(subprocess, son)
                subprocess.process_id = process_id
                subprocess.survey_id = survey_id
                process.subprocesses.append(subprocess)
                session.add(subprocess)
                session.flush()
                session.expunge(subprocess)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(subprocess.id)

    @handlers.authz('author')
    def put(self, subprocess_id):
        '''
        Update an existing subprocess.
        '''
        if subprocess_id == '':
            self.ordering()
            return

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                subprocess = session.query(model.Subprocess).get(subprocess_id)
                if subprocess is None:
                    raise ValueError("No such object")
                self._update(subprocess, son)
                session.add(subprocess)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such subprocess")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(subprocess_id)

    def ordering(self):
        '''
        Update an existing function.
        '''
        survey_id = self.get_survey_id()
        if not is_current_survey(survey_id):
            raise handlers.MethodError("This surveyId is not current one.")

        process_id = self.get_argument("processId", "")
        if process_id == None:
            raise handlers.MethodError("Process ID is required.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                process = session.query(model.Process)\
                    .filter_by(id=process_id, survey_id=survey_id).one()
                reorder(process.subprocesses, son)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query(process_id)

    def get_survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required.")

        return survey_id

    def _update(self, subprocess, son):
        '''
        Apply subprocess-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            subprocess.title = son['title']
        if son.get('description', '') != '':
            subprocess.description = son['description']
