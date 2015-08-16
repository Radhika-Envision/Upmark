import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.assessment')


class AssessmentHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, assessment_id):
        if assessment_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)

                if assessment is None:
                    raise ValueError("No such object")
                if assessment.organisation.id != self.organisation.id:
                    self.check_privillege('author', 'consultant')
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such assessment")

            to_son = ToSon(include=[
                # Any
                r'/id$',
                r'/title$',
                r'/name$',
                r'/description$',
                r'/approval$',
                # Nested
                r'/survey$',
                r'/organisation$',
                r'/hierarchy$',
                r'/hierarchy/structure.*$'
            ])
            son = to_son(assessment)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get a list.'''

        survey_id = self.get_argument('surveyId', '')
        org_id = self.get_argument('orgId', '')
        if self.current_user.role in {'clerk', 'org_admin'}:
            if org_id == '':
                org_id = str(self.organisation.id)
            elif org_id != str(self.organisation.id):
                raise AuthzError(
                    "You can't view another organisation's assessments")

        with model.session_scope() as session:
            query = session.query(model.Assessment)

            if survey_id != '':
                query = query.filter_by(survey_id=survey_id)

            if org_id != '':
                query = query.filter_by(organisation_id=org_id)

            query = query.order_by(model.Assessment.created)
            query = self.paginate(query)

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/name$',
                # Descend
                r'/[0-9]+$',
                r'/organisation$'
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('clerk')
    def post(self, assessment_id):
        '''Create new.'''
        if assessment_id != '':
            raise handlers.MethodError("Can't use POST for existing object")

        survey_id = self.get_argument('surveyId', '')
        if survey_id == '':
            raise handlers.MethodError("Survey ID is required")
        hierarchy_id = self.get_argument('hierarchyId', '')
        if hierarchy_id == '':
            raise handlers.MethodError("Hierarchy ID is required")
        org_id = self.get_argument('orgId', '')
        if org_id == '':
            raise handlers.MethodError("Organisation ID is required")

        try:
            with model.session_scope() as session:
                assessment = model.Assessment(
                    survey_id=survey_id, hierarchy_id=hierarchy_id,
                    organisation_id=org_id)
                self._update(assessment, self.request_son)
                session.add(assessment)
                session.flush()
                assessment_id = str(assessment.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id)

    @handlers.authz('clerk')
    def put(self, assessment_id):
        '''Update existing.'''
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID required")

        try:
            with model.session_scope() as session:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)
                if assessment is None:
                    raise ValueError("No such object")
                self._update(assessment, self.request_son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such assessment")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id)

    @handlers.authz('org_admin')
    def delete(self, assessment_id):
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID required")

        try:
            with model.session_scope() as session:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)
                if assessment is None:
                    raise ValueError("No such object")
                session.delete(assessment)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("This assessment is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such assessment")

        self.finish()

    def _check_update(self, assessment, son):
        if assessment.approval != son['approval']:
            if (self.current_user.role == 'org_admin' and
                son['approval'] not in {'draft', 'final'}):
                    raise handlers.AuthzError(
                        "You can't approve this assessment.")
            elif (self.current_user.role == 'consultant' and
                  son['approval'] not in {'draft', 'final', 'reviewed'}):
                    raise handlers.AuthzError(
                        "You can't approve this assessment.")
            elif self.has_privillege('authority'):
                pass
            else:
                raise handlers.AuthzError(
                    "You can't approve this assessment.")

    def _update(self, assessment, son):
        update = updater(assessment)
        update('title', son)
        update('approval', son)
