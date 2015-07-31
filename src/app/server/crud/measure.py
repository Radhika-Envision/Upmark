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

import crud
from utils import denormalise, falsy, reorder, ToSon, updater


def update_measure(measure, son):
    '''
    Apply user-provided data to the saved model.
    '''
    update = updater(measure)
    update('title', son)
    update('intent', son)
    update('inputs', son)
    update('scenario', son)
    update('questions', son)
    update('response_type', son)


class MeasureHandler(crud.survey.SurveyCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, measure_id):
        '''Get a single measure.'''

        if measure_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.survey_id))
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such measure")

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                # Fields to match from only the root object
                r'^/intent$',
                r'^/inputs$',
                r'^/scenario$',
                r'^/questions$',
                r'^/weight$',
                r'^/response_type$',
                # Descend into nested objects
                r'/parents$',
                r'/parent$',
                r'/hierarchy$',
                r'/hierarchy/survey$'
            ])
            son = to_son(measure)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get a list.'''
        qnode_id = self.get_argument('qnodeId', '')
        orphans = not falsy(self.get_argument('orphans', ''))

        sons = []
        with model.session_scope() as session:
            if qnode_id != '':
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.survey_id))
                measures = qnode.measures
            elif orphans:
                measures = session.query(model.Measure)\
                    .outerjoin(model.QnodeMeasure)\
                    .filter(model.Measure.survey_id == survey.id)\
                    .filter(model.QnodeMeasure.qnode_id == None)\
                    .all()
            else:
                measures = session.query(model.Measure)\
                    .filter_by(survey_id=self.survey_id)\
                    .all()

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/survey$',
            ])
            son = to_son(measures)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, measure_id):
        '''Create new.'''
        if measure_id != '':
            raise handlers.MethodError(
                "Can't specify ID when creating a new measure.")

        son = denormalise(json_decode(self.request.body))

        try:
            with model.session_scope() as session:
                measure = model.Measure(survey_id=self.survey_id)
                self._update(measure, son)
                session.flush()

                for qnode_son in son['parents']:
                    qnode = session.query(model.QuestionNode)\
                        .get((qnode_son['id'], self.survey_id))
                    if qnode is None:
                        raise handlers.ModelError("No such question node")
                    qnode.measures.append(measure)
                    qnode.measures.reorder()
                measure_id = str(measure.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    @handlers.authz('author')
    def delete(self, measure_id):
        '''Delete an existing measure.'''
        if measure_id == '':
            raise handlers.MethodError("Measure ID required")

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.survey_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")
                session.delete(measure)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Measure is in use")
        except sqlalchemy.exc.StatementError:
            raise handlers.MissingDocError("No such measure")

        self.finish()

    @handlers.authz('author')
    def put(self, measure_id):
        '''Update existing.'''

        if measure_id == '':
            self.ordering()
            return

        son = denormalise(json_decode(self.request.body))

        survey_id = self.get_survey_id()
        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, survey_id))
                if measure is None:
                    raise ValueError("No such object")
                self._update(measure, son)
                session.add(measure)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such measure")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    def ordering(self):
        '''Change the order that would be returned by a query.'''
        survey_id = self.get_survey_id()
        if not is_current_survey(survey_id):
            raise handlers.MethodError("This surveyId is not current one.")

        subprocess_id = self.get_argument("subprocessId", "")
        if subprocess_id == None:
            raise handlers.MethodError("Subprocess ID is required.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                subprocess = session.query(model.Subprocess)\
                    .get((subprocess_id, survey_id))
                reorder(subprocess.measures, son)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.get()
