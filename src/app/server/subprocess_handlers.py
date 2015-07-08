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
            son = json_decode(self.request.body)
            process_id = son['process']['id']
            if process_id == None:
                raise handlers.MethodError("Can't GET subprocess without process id.")

            self.query(process_id)
            return

        survey_id = self.check_survey_id()
        is_current = False
        if survey_id == str(get_current_survey()):
            is_current = True

        with model.session_scope() as session:
            try:
                if is_current:
                    subprocessModel = model.Subprocess
                else:
                    subprocessModel = model.Subprocess.__history_mapper__.class_
                
                subprocess = session.query(subprocessModel).filter_by(id = subprocess_id, survey_id = survey_id).one()

                if subprocess is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such subprocess")


            if is_current:
                processModel = model.Process
            else:
                processModel = model.Process.__history_mapper__.class_

            if is_current:
                functionModel = model.Function
            else:
                functionModel = model.Function.__history_mapper__.class_

            if is_current:
                surveyModel = model.Survey
            else:
                surveyModel = model.Survey.__history_mapper__.class_

            process = session.query(processModel).filter_by(id = subprocess.process_id, survey_id = survey_id).one()
            function = session.query(functionModel).filter_by(id = process.function_id, survey_id = survey_id).one()
            survey = session.query(surveyModel).filter_by(id = survey_id).one()
            
            survey_json = to_dict(survey, include={'id', 'title'})
            survey_json = simplify(survey_json)
            survey_json = normalise(survey_json)

            function_json = to_dict(function, include={'id', 'title', 'seq', 'description'})
            function_json = simplify(function_json)
            function_json = normalise(function_json)
            function_json['survey'] = survey_json

            process_json = to_dict(process, include={'id', 'title', 'seq', 'description'})
            process_json = simplify(process_json)
            process_json = normalise(process_json)
            process_json['function'] = function_json

            son = to_dict(subprocess, include={'id', 'title', 'seq', 'description'})
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

        son = json_decode(self.request.body)
        process_id = son['process']['id']
        if process_id == None:
            raise handlers.MethodError("Can't use POST subprocess without process id.")

        

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
        son = json_decode(self.request.body)
        survey_id = son['process']['function']['survey']['id']
        if survey_id == '':
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
