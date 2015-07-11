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
                subprocess = session.query(model.Subprocess)\
                    .filter_by(id=subprocess_id, survey_id=survey_id).one()

                if subprocess is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such subprocess")

            process = subprocess.process
            function = process.function
            survey = function.survey
            
            survey_json = to_dict(survey, include={'id', 'title'})

            function_json = to_dict(function, include={'id', 'title', 'seq'})
            function_json['survey'] = survey_json

            process_json = to_dict(process, include={'id', 'title', 'seq'})
            process_json['function'] = function_json

            son = to_dict(subprocess, include={
                'id', 'title', 'seq', 'description'})
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
            query = session.query(model.Subprocess)\
                .filter_by(process_id=process_id, survey_id=survey_id)\
                .order_by(model.Subprocess.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Subprocess.title.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq'})
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
                process = session.query(model.Process)\
                    .get((process_id, survey_id))
                subprocess = model.Subprocess()
                self._update(subprocess, son)
                subprocess.process_id = process_id
                subprocess.survey_id = survey_id
                process.subprocesses.append(subprocess)
                session.flush()
                session.expunge(subprocess)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(subprocess.id)

    @handlers.authz('author')
    def delete(self, subprocess_id):
        '''
        Delete an existing subprocess.
        '''
        if subprocess_id == '':
            raise handlers.MethodError("Subprocess ID required")
        survey_id = self.get_survey_id()
        try:
            with model.session_scope() as session:
                subprocess = session.query(model.Subprocess)\
                    .get((subprocess_id, survey_id))
                if subprocess is None:
                    raise ValueError("No such object")
                session.delete(subprocess)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Subprocess is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such subprocess")

        self.finish()

    @handlers.authz('author')
    def put(self, subprocess_id):
        '''
        Update an existing subprocess.
        '''
        if subprocess_id == '':
            self.ordering()
            return

        son = json_decode(self.request.body)

        survey_id = self.get_survey_id()
        try:
            with model.session_scope() as session:
                subprocess = session.query(model.Subprocess)\
                    .get((subprocess_id, survey_id))
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
                    .get((process_id, survey_id))
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
