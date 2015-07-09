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

from utils import to_dict, simplify, normalise, denormalise,\
        is_current_survey, get_model

class MeasureHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, measure_id):
        '''
        Get a single measure.
        '''
        if measure_id == "":
            self.query()
            return

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        with model.session_scope() as session:
            try:
                measureModel = get_model(is_current, model.Measure)
                measure = session.query(measureModel)\
                    .filter_by(id=measure_id, survey_id=survey_id).one()
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such measure")

            subprocessModel = get_model(is_current, model.Subprocess)
            processModel = get_model(is_current, model.Process)
            functionModel = get_model(is_current, model.Function)
            surveyModel = get_model(is_current, model.Survey)

            subprocess = session.query(subprocessModel)\
                .filter_by(id=measure.subprocess_id, survey_id=survey_id)\
                .one()
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

            subprocess_json = to_dict(subprocess, include={'id', 'title', 'seq'})
            subprocess_json = simplify(subprocess_json)
            subprocess_json = normalise(subprocess_json)
            subprocess_json['process'] = process_json

            son = to_dict(measure, include={
                'id', 'title', 'seq',
                'intent', 'inputs', 'scenario', 'questions',
                'weight', 'response_type'})
            son = simplify(son)
            son = normalise(son)
            son['subprocess'] = subprocess_json
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list.
        '''

        survey_id = self.get_survey_id()
        is_current = is_current_survey(survey_id)

        subprocess_id = self.get_argument("subprocessId", "")
        if subprocess_id == None:
            raise handlers.MethodError("Subprocess ID is required.")

        sons = []
        with model.session_scope() as session:
            measureModel = get_model(is_current, model.Measure)
            query = session.query(measureModel)\
                .filter_by(subprocess_id=subprocess_id, survey_id=survey_id)\
                .order_by(measureModel.seq)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq'})
                son = simplify(son)
                son = normalise(son)
                # son["category"] = org
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, measure_id):
        '''
        Create new.
        '''
        if measure_id != '':
            raise handlers.MethodError("Can't use POST for existing measure.")

        survey_id = self.get_survey_id()

        subprocess_id = self.get_argument('subprocessId', None)
        if subprocess_id == None:
            raise handlers.MethodError("subprocessId is required")

        son = json_decode(self.request.body)
        son = denormalise(son)

        try:
            with model.session_scope() as session:
                # This is OK because POST is always for the current survey
                subprocess = session.query(model.Subprocess).get(subprocess_id)
                measure = model.Measure()
                self._update(measure, son)
                measure.subprocess_id = subprocess_id
                measure.survey_id = survey_id
                subprocess.measures.append(measure)
                session.add(measure)
                session.flush()
                session.expunge(measure)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure.id)

    @handlers.authz('author')
    def put(self, measure_id):
        '''
        Update existing.
        '''
        if measure_id == '':
            raise handlers.MethodError("Can't use PUT for new measure (no ID).")
        son = json_decode(self.request.body)
        son = denormalise(son)

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure).get(measure_id)
                if measure is None:
                    raise ValueError("No such object")
                self._update(measure, son)
                session.add(measure)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such measure")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    def _update(self, measure, son):
        '''
        Apply user-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            measure.title = son['title']
        if son.get('weight', '') != '':
            measure.weight = son['weight']
        if son.get('intent', '') != '':
            measure.intent = son['intent']
        if son.get('inputs', '') != '':
            measure.inputs = son['inputs']
        if son.get('scenario', '') != '':
            measure.scenario = son['scenario']
        if son.get('questions', '') != '':
            measure.questions = son['questions']
        if son.get('response_type', '') != '':
            measure.response_type = son['response_type']

    def get_survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required.")

        return survey_id
