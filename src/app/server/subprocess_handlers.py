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


class SubprocessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, subprocess_id):
        '''
        Get a single subprocess.
        '''
        if subprocess_id == "":
            process_id = self.get_argument('processId', None)
            if process_id == None:
                raise handlers.MethodError("Can't GET subprocess without process id.")

            self.query(process_id)
            return

        survey_id = self.check_survey_id()

        with model.session_scope() as session:
            try:
                if survey_id == str(get_current_survey()):
                    subprocess = session.query(model.Subprocess).filter_by(id = subprocess_id, survey_id = survey_id).one()
                else:
                    SubprocessHistory = model.Subprocess.__history_mapper__.class_
                    subprocess = session.query(SubprocessHistory).filter_by(id = subprocess_id, survey_id = survey_id).one()

                if subprocess is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such subprocess")

            son = to_dict(subprocess, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, process_id):
        '''
        Get a list of subprocesss.
        '''
        survey_id = self.check_survey_id()

        sons = []
        with model.session_scope() as session:
            if survey_id == str(get_current_survey()):
                query = session.query(model.Subprocess).filter_by(process_id = process_id, survey_id = survey_id).order_by(model.Subprocess.seq)
            else:
                SubprocessHistory = model.Subprocess.__history_mapper__.class_
                query = session.query(SubprocessHistory).filter_by(process_id = process_id, survey_id = survey_id).order_by(SubprocessHistory.seq)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Subprocess.title.ilike(r'%{}%'.format(term)))

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
    def post(self, subprocess_id):
        '''
        Create a new subprocess.
        '''
        if subprocess_id != '':
            raise handlers.MethodError("Can't use POST for existing subprocess.")

        survey_id = self.check_survey_id()

        process_id = self.get_argument('processId', None)
        if process_id == None:
            raise handlers.MethodError("Can't use POST subprocess without process id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                subprocess = model.Subprocess()
                self._update(subprocess, son)
                subprocess.process_id = process_id
                subprocess.survey_id = survey_id
                session.add(subprocess)
                session.flush()
                session.expunge(subprocess)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.finish(str(subprocess.id))

    @handlers.authz('author')
    def put(self, subprocess_id):
        '''
        Update an existing subprocess.
        '''
        if subprocess_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new subprocess (no ID).")
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

    def check_survey_id(self):
        survey_id = self.get_argument('surveyId', None)
        if survey_id == None:
            raise handlers.MethodError("Can't GET function without survey id.")
        return survey_id

    def _update(self, subprocess, son):
        '''
        Apply subprocess-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            subprocess.title = son['title']
        if son.get('seq', '') != '':
            subprocess.seq = son['seq']
        if son.get('description', '') != '':
            subprocess.description = son['description']
        if son.get('process_id', '') != '':
            subprocess.process_id = son['process_id']
