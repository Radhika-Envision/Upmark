from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import uuid

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.assessment')

MAX_WORKERS = 4


class AssessmentHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

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
                r'/n_measures$',
                r'/survey/tracking_id$',
                # Nested
                r'/survey$',
                r'/survey/tracking_id$',
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
        term = self.get_argument('term', '')
        survey_id = self.get_argument('surveyId', '')
        hierarchy_id = self.get_argument('hierarchyId', '')
        approval = self.get_argument('approval', '')
        tracking_id = self.get_argument('trackingId', '')

        org_id = self.get_argument('orgId', '')
        if self.current_user.role in {'clerk', 'org_admin'}:
            if org_id == '':
                org_id = str(self.organisation.id)
            elif org_id != str(self.organisation.id):
                raise handlers.AuthzError(
                    "You can't view another organisation's submissions")

        with model.session_scope() as session:
            query = session.query(model.Assessment)

            if term != '':
                query = query.filter(
                    model.Assessment.title.ilike(r'%{}%'.format(term)))

            if survey_id != '':
                query = query.filter_by(survey_id=survey_id)

            if hierarchy_id != '':
                query = query.filter_by(hierarchy_id=hierarchy_id)

            if approval != '':
                approval_set = self.approval_set(approval)
                log.warn('Approval set: %s', approval_set)
                query = query.filter(
                    model.Assessment.approval.in_(approval_set))

            if org_id != '':
                query = query.filter_by(organisation_id=org_id)

            if tracking_id != '':
                query = query.join(model.Survey)
                query = query.filter(model.Survey.tracking_id == tracking_id)

            query = query.order_by(model.Assessment.created.desc())
            query = self.paginate(query)

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/name$',
                r'/approval$',
                r'/created$',
                r'/survey/tracking_id$',
                # Descend
                r'/[0-9]+$',
                r'/organisation$',
                r'/hierarchy$',
                r'/survey$'
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, assessment_id):
        '''Create new.'''
        if assessment_id != '':
            raise handlers.MethodError("Can't use POST for existing object")

        survey_id = self.get_argument('surveyId', '')
        if survey_id == '':
            raise handlers.ModelError("Survey ID is required")

        hierarchy_id = self.get_argument('hierarchyId', '')
        if hierarchy_id == '':
            raise handlers.ModelError("Hierarchy ID is required")

        org_id = self.get_argument('orgId', '')
        if org_id == '':
            raise handlers.ModelError("Organisation ID is required")

        duplicate_id = self.get_argument('duplicateId', '')

        if org_id != str(self.organisation.id):
            self.check_privillege('consultant')

        try:
            with model.session_scope() as session:
                self._check_open(survey_id, hierarchy_id, org_id, session)

                assessment = model.Assessment(
                    survey_id=survey_id, hierarchy_id=hierarchy_id,
                    organisation_id=org_id, approval='draft')
                self._update(assessment, self.request_son)
                session.add(assessment)
                session.flush()
                assessment_id = str(assessment.id)

                if duplicate_id != '':
                    yield AssessmentHandler.executor.submit(
                        self.duplicate, assessment, duplicate_id, session)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id)

    def _check_open(self, survey_id, hierarchy_id, org_id, session):
        purchased_survey = (session.query(model.PurchasedSurvey)
            .filter_by(survey_id=survey_id,
                       hierarchy_id=hierarchy_id,
                       organisation_id=org_id)
            .first())
        if not purchased_survey:
            raise handlers.ModelError(
                "Survey is not open: it needs to be purchased")

    def duplicate(self, assessment, duplicate_id, session):
        s_assessment = (session.query(model.Assessment)
                .filter_by(id=duplicate_id)
                .first())
        if s_assessment is None:
            raise handlers.MissingDocError(
                "Source submission (for duplication) no found")

        if str(s_assessment.organisation_id) != (assessment.organisation_id):
            raise handlers.ModelError(
                "Can't duplicate a submission across two organisations: "
                "'%s/%s' and '%s/%s'" % (
                    s_assessment.organisation.name,
                    assessment.organisation.name))

        hierarchy_id = str(assessment.hierarchy.id)
        measure_ids = {str(m.id) for m in assessment.survey.measures
                       if any(str(p.hierarchy_id) == hierarchy_id
                              for p in m.parents)}

        qnode_ids = {str(r[0]) for r in
                session.query(model.QuestionNode.id)
                    .filter_by(survey_id=assessment.survey_id,
                               hierarchy_id=assessment.hierarchy_id)
                    .all()}

        s_rnodes = (session.query(model.ResponseNode)
                .filter_by(assessment_id=s_assessment.id)
                .filter(model.ResponseNode.qnode_id.in_(qnode_ids))
                .all())

        for rnode in s_rnodes:
            # Duplicate
            session.expunge(rnode)
            make_transient(rnode)
            rnode.id = None

            # Customise
            rnode.survey = assessment.survey
            rnode.assessment = assessment
            session.add(rnode)
            session.flush()
            # No need to flush because no dependencies

        for response in s_assessment.responses:
            if str(response.measure_id) not in measure_ids:
                continue

            attachments = list(response.attachments)

            # Fetch lazy-loaded fields
            response.comment

            # Duplicate
            session.expunge(response)
            make_transient(response)
            response.id = None

            # Customise
            response.survey = assessment.survey
            response.assessment = assessment
            response.approval = 'draft'

            session.add(response)
            session.flush()

            # Same thing for attachments
            for attachment in attachments:
                # Fetch lazy-loaded fields
                attachment.blob

                # Duplicate
                session.expunge(attachment)
                make_transient(attachment)
                attachment.id = None

                # Customise
                attachment.response = response

                session.add(attachment)

        session.flush()
        assessment.update_stats_descendants()

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
                    raise handlers.ModelError("No such submission")
                self._check_modify(assessment)
                if approval != '':
                    self._check_approval(session, assessment, approval)
                    self._set_approval(assessment, approval)
                self._update(assessment, self.request_son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such submission")
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
                    raise handlers.ModelError("No such submission")
                self._check_delete(assessment)
                session.delete(assessment)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("This submission is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such submission")

        self.finish()

    def _check_delete(self, assessment):
        if assessment.organisation.id != self.organisation.id:
            self.check_privillege('admin')

    def _check_modify(self, assessment):
        if assessment.organisation.id != self.organisation.id:
            self.check_privillege('consultant')

    def _check_approval(self, session, assessment, approval):
        approval_set = self.approval_set(approval)

        n_relevant_responses = (session.query(model.Response)
                 .filter(model.Response.assessment_id == assessment.id,
                         model.Response.approval.in_(approval_set))
                 .count())
        n_measures = (session.query(model.QnodeMeasure.measure_id)
                .join(model.QuestionNode)
                .filter(model.QuestionNode.hierarchy_id ==
                            assessment.hierarchy_id,
                        model.QuestionNode.survey_id == assessment.survey_id,
                        model.QnodeMeasure.survey_id == assessment.survey_id,
                        model.QnodeMeasure.qnode_id == model.QuestionNode.id)
                .distinct()
                .count())

        if n_relevant_responses < n_measures:
            raise handlers.ModelError(
                "%d of %d responses are incomplete" %
                (n_measures - n_relevant_responses, n_measures))

    def approval_set(self, minimum):
        order = ['draft', 'final', 'reviewed', 'approved']
        return order[order.index(minimum):]

    def _set_approval(self, assessment, approval):
        if self.current_user.role == 'org_admin':
            if approval not in {'draft', 'final'}:
                raise handlers.AuthzError(
                    "You can't mark this submission as %s." % approval)
        elif self.current_user.role == 'consultant':
            if approval not in {'draft', 'final', 'reviewed'}:
                raise handlers.AuthzError(
                    "You can't mark this submission as %s." % approval)
        elif self.has_privillege('authority'):
            pass
        else:
            raise handlers.AuthzError(
                "You can't mark this submission as %s." % approval)
        assessment.approval = approval

    def _update(self, assessment, son):
        update = updater(assessment)
        update('title', son)
