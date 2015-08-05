import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

import handlers
import model
import logging

from utils import ToSon, truthy, updater

log = logging.getLogger('app.crud.surveys')


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

    def check_open(self):
        if not self.survey.is_open:
            raise handlers.MethodError("This survey is not open for responses")


class SurveyHandler(handlers.Paginate, handlers.BaseHandler):

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

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/description$',
                r'/created$',
                r'/finalised_date$',
                r'/open_date$'
            ])
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
        is_open = truthy(self.get_argument('open', ''))
        is_editable = truthy(self.get_argument('editable', ''))

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Survey)
            if term != '':
                query = query.filter(
                    model.Survey.title.ilike(r'%{}%'.format(term)))

            if is_open:
                query = query.filter(model.Survey.open_date!=None)

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

                if duplicate_id != '':
                    source_survey = (session.query(model.Survey)
                        .get(duplicate_id))
                    self.duplicate_structure(source_survey, survey, session)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def duplicate_structure(self, source_survey, target_survey, session):
        '''
        Duplicate an existing survey - just the structure (e.g. hierarchy,
        qnodes and measures).
        '''
        log.info('Duplicating %s from %s', target_survey, source_survey)

        def dissociate(entity):
            # Expunge followed by make_transient tells SQLAlchemy to use INSERT
            # instead of UPDATE, thus duplicating the row in the table.
            session.expunge(entity)
            make_transient(entity)
            session.add(entity)
            return entity

        def dup_hierarchies(hierarchies):
            for hierarchy in source_survey.hierarchies:
                log.info('Duplicating %s', hierarchy)
                qs = hierarchy.qnodes
                dissociate(hierarchy)
                hierarchy.survey_id = target_survey.id
                session.flush()
                dup_qnodes(qs)

        def dup_qnodes(qnodes):
            for qnode in qnodes:
                log.info('Duplicating %s', qnode)
                children = qnode.children
                qnode_measures = qnode.qnode_measures
                dissociate(qnode)
                qnode.survey_id = target_survey.id
                session.flush()
                dup_qnodes(children)
                dup_qnode_measures(qnode_measures)

        def dup_qnode_measures(qnode_measures):
            for qnode_measure in qnode_measures:
                log.info('Duplicating %s', qnode_measure)
                dissociate(qnode_measure)
                qnode_measure.survey_id = target_survey.id
            session.flush()

        def dup_measures(measures):
            for measure in measures:
                log.info('Duplicating %s', measure)
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

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey).get(survey_id)
                if survey is None:
                    raise ValueError("No such object")
                self._update(survey, self.request_son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(survey_id)

    def _update(self, survey, son):
        '''
        Apply survey-provided data to the saved model.
        '''
        update = updater(survey)
        update('title', son)
        update('description', son)


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
                .filter(self.mapper.id==entity_id))

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/is_open$',
                r'/is_editable$',
                # Descend
                r'/[0-9]+$',
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
