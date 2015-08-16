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


class AssessmentCentric:
    @property
    def assessment_id(self):
        assessment_id = self.get_argument("assessmentId", "")
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID is required")

        return assessment_id

    @property
    def assessment(self):
        if not hasattr(self, '_assessment'):
            with model.session_scope() as session:
                assessment = session.query(model.Assessment).get(
                    self.assessment_id)
                if assessment is None:
                    raise handlers.MissingDocError("No such assessment")
                session.expunge(assessment)
            self._assessment = assessment
        return self._assessment

    @property
    def survey_id(self):
        survey_id = self.get_argument("surveyId", "")
        if survey_id != '':
            return survey_id

        assessment_id = self.get_argument("assessmentId", "")
        log.warn('s: %s, a:%s', survey_id, assessment_id)
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID or survey ID required")

        return str(self.assessment.survey_id)


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
                    organisation_id=org_id, approval='draft')
                self._update(assessment, self.request_son)
                session.add(assessment)
                session.flush()
                assessment_id = str(assessment.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id)

    @tornado.web.authenticated
    def put(self, assessment_id):
        '''Update existing.'''
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID required")

        approval = self.get_argument('approval', '')

        try:
            with model.session_scope() as session:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)
                if assessment is None:
                    raise ValueError("No such object")
                self._check_modify(assessment)
                if approval != '':
                    self._set_approval(assessment, approval)
                self._update(assessment, self.request_son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such assessment")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id)

    @tornado.web.authenticated
    def delete(self, assessment_id):
        if assessment_id == '':
            raise handlers.MethodError("Assessment ID required")

        try:
            with model.session_scope() as session:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)
                if assessment is None:
                    raise ValueError("No such object")
                self._check_delete(assessment)
                session.delete(assessment)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("This assessment is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such assessment")

        self.finish()

    def _check_delete(self, assessment):
        if assessment.organisation.id != self.organisation.id:
            self.check_privillege('admin')

    def _check_modify(self, assessment):
        if assessment.organisation.id != self.organisation.id:
            self.check_privillege('consultant')

    def _set_approval(self, assessment, approval):
        if self.current_user.role == 'org_admin':
            if approval not in {'draft', 'final'}:
                raise handlers.AuthzError(
                    "You can't mark this assessment as %s." % approval)
        elif self.current_user.role == 'consultant':
            if approval not in {'draft', 'final', 'reviewed'}:
                raise handlers.AuthzError(
                    "You can't mark this assessment as %s." % approval)
        elif self.has_privillege('authority'):
            pass
        else:
            raise handlers.AuthzError(
                "You can't mark this assessment as %s." % approval)
        assessment.approval = approval

    def _update(self, assessment, son):
        update = updater(assessment)
        update('title', son)
