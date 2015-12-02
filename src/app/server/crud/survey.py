from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import time
import uuid

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient
import voluptuous

import handlers
import model
import crud.activity

from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.survey')

MAX_WORKERS = 4


class SurveyCentric:
    '''
    Mixin for handlers that deal with models that have a survey ID as part of
    a composite primary key.
    '''
    @property
    def survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required")

        return survey_id

    @property
    def survey(self):
        if not hasattr(self, '_survey'):
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(self.survey_id)
                if survey is None:
                    raise handlers.MissingDocError("No such survey")
                session.expunge(survey)
            self._survey = survey
        return self._survey

    def check_editable(self):
        if not self.survey.is_editable:
            raise handlers.MethodError("This survey is closed for editing")


class SurveyHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, survey_id):
        '''
        Get a single survey.
        '''
        if survey_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                query = session.query(model.Survey)
                survey = query.get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such survey")

            exclude = []
            if not self.has_privillege('author'):
                exclude += [
                    r'/response_types.*score$',
                    r'/response_types.*formula$'
                ]

            to_son = ToSon(include=[
                r'/id$',
                r'/tracking_id$',
                r'/title$',
                r'/description$',
                r'/created$',
                r'/is_editable$',
                r'/response_types.*$'
            ], exclude=exclude)
            son = to_son(survey)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list of surveys.
        '''

        term = self.get_argument('term', '')
        is_editable = truthy(self.get_argument('editable', ''))

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Survey)
            if term != '':
                query = query.filter(
                    model.Survey.title.ilike(r'%{}%'.format(term)))

            if is_editable:
                query = query.filter(model.Survey.finalised_date==None)

            query = query.order_by(model.Survey.created.desc())
            query = self.paginate(query)

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/description$',
                r'/[0-9]+$'
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    @gen.coroutine
    def post(self, survey_id):
        '''
        Create a new survey.
        '''
        if survey_id != '':
            raise handlers.MethodError("Can't use POST for existing survey.")

        duplicate_id = self.get_argument('duplicateId', '')

        try:
            with model.session_scope() as session:
                survey = model.Survey()
                self._update(survey, self.request_son)
                session.add(survey)
                session.flush()
                survey_id = str(survey.id)

                act = crud.activity.Activities(session)

                if duplicate_id != '':
                    source_survey = (session.query(model.Survey)
                        .get(duplicate_id))
                    if source_survey is None:
                        raise handlers.MissingDocError(
                            "Source survey does not exist")
                    yield self.duplicate_structure(
                        source_survey, survey, session)
                    source_survey.finalised_date = datetime.datetime.utcnow()
                    act.record(self.current_user, source_survey, ['state'])

                act.record(self.current_user, survey, ['create'])
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey)
                    self.reason("Subscribed to program")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    @run_on_executor
    def duplicate_structure(self, source_survey, target_survey, session):
        '''
        Duplicate an existing survey - just the structure (e.g. hierarchy,
        qnodes and measures).
        '''
        log.debug('Duplicating %s from %s', target_survey, source_survey)

        target_survey.tracking_id = source_survey.tracking_id

        def dissociate(entity):
            # Expunge followed by make_transient tells SQLAlchemy to use INSERT
            # instead of UPDATE, thus duplicating the row in the table.
            session.expunge(entity)
            make_transient(entity)
            session.add(entity)
            return entity

        def dup_hierarchies(hierarchies):
            for hierarchy in source_survey.hierarchies:
                log.debug('Duplicating %s', hierarchy)
                qs = hierarchy.qnodes
                dissociate(hierarchy)
                hierarchy.survey_id = target_survey.id
                session.flush()
                dup_qnodes(qs)

        def dup_qnodes(qnodes):
            for qnode in qnodes:
                log.debug('Duplicating %s', qnode)
                children = qnode.children
                qnode_measures = qnode.qnode_measures
                dissociate(qnode)
                qnode.survey_id = target_survey.id
                session.flush()
                dup_qnodes(children)
                dup_qnode_measures(qnode_measures)

        def dup_qnode_measures(qnode_measures):
            for qnode_measure in qnode_measures:
                log.debug('Duplicating %s', qnode_measure)
                dissociate(qnode_measure)
                qnode_measure.survey_id = target_survey.id
            session.flush()

        def dup_measures(measures):
            for measure in measures:
                log.debug('Duplicating %s', measure)
                dissociate(measure)
                measure.survey_id = target_survey.id
            session.flush()

        dup_measures(source_survey.measures)
        dup_hierarchies(source_survey.hierarchies)

    @handlers.authz('author')
    def delete(self, survey_id):
        '''
        Delete an existing survey.
        '''
        if survey_id == '':
            raise handlers.MethodError("Survey ID required")

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey)\
                    .get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
                if not survey.is_editable:
                    raise handlers.MethodError(
                        "This survey is closed for editing")
                act = crud.activity.Activities(session)
                act.record(self.current_user, survey, ['delete'])
                for hierarchy in survey.hierarchies:
                    hierarchy.modified = datetime.datetime.utcnow()
                session.delete(survey)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Survey is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")

        self.finish()

    @handlers.authz('author')
    def put(self, survey_id):
        '''
        Update an existing survey.
        '''
        if survey_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new survey (no ID).")

        editable = self.get_argument('editable', '')
        if editable != '':
            self._update_state(survey_id, editable)
            return

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")

                if not survey.is_editable:
                    raise handlers.MethodError(
                        "This survey is closed for editing")
                self._update(survey, self.request_son)

                act = crud.activity.Activities(session)
                if session.is_modified(survey):
                    act.record(self.current_user, survey, ['update'])
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey)
                    self.reason("Subscribed to program")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def _update_state(self, survey_id, editable):
        '''
        Just update the state of the survey (not title etc.)
        '''
        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")

                if editable != '':
                    if truthy(editable):
                        survey.finalised_date = None
                    else:
                        survey.finalised_date = datetime.datetime.utcnow()

                act = crud.activity.Activities(session)
                if session.is_modified(survey):
                    act.record(self.current_user, survey, ['state'])
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey)
                    self.reason("Subscribed to program")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def _update(self, survey, son):
        '''
        Apply survey-provided data to the saved model.
        '''
        if survey.response_types != son['response_types']:
            for hierarchy in survey.hierarchies:
                hierarchy.modified = datetime.datetime.utcnow()
        update = updater(survey)
        update('title', son)
        update('description', son)
        try:
            update('response_types', son)
        except voluptuous.Error as e:
            raise handlers.ModelError("Response types are invalid: %s" % str(e))


class SurveyTrackingHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id):
        '''
        Get a list of surveys that share the same lineage.
        '''
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required")

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            if survey is None:
                raise handlers.MissingDocError("No such survey")

            query = (session.query(model.Survey)
                .filter(model.Survey.tracking_id==survey.tracking_id)
                .order_by(model.Survey.created))

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/is_editable$',
                # Descend
                r'/[0-9]+$',
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()


class SurveyHistoryHandler(handlers.BaseHandler):
    def initialize(self, mapper):
        self.mapper = mapper

    @tornado.web.authenticated
    def get(self, entity_id):
        '''
        Get a list of surveys that some entity belongs to. For example,
        a single hierarchy may be present in multiple surveys.
        '''
        with model.session_scope() as session:
            query = (session.query(model.Survey)
                .join(self.mapper)
                .filter(self.mapper.id==entity_id)
                .order_by(model.Survey.created))

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/is_editable$',
                r'/created$',
                # Descend
                r'/[0-9]+$',
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
