from concurrent.futures import ThreadPoolExecutor
import datetime
import random
import time
import uuid

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

from activity import Activities
import crud.program
import errors
import handlers
import model
import logging

from score import Calculator
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.submission')

MAX_WORKERS = 4


class SubmissionHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, submission_id):
        if submission_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                submission = session.query(model.Submission)\
                    .get(submission_id)

                if submission is None:
                    raise ValueError("No such object")
                if submission.organisation.id != self.organisation.id:
                    self.check_privillege('author', 'consultant')
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise errors.MissingDocError("No such submission")

            to_son = ToSon(
                # Any
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/name$',
                r'</description$',
                r'/approval$',
                r'/created$',
                r'/deleted$',
                r'/n_measures$',
                r'^/error$',
                r'^/survey/error$',
                r'/program/tracking_id$',
                # Nested
                r'/program$',
                r'/program/tracking_id$',
                r'/organisation$',
                r'/survey$',
                r'/survey/structure.*$',
                r'/survey/min_stats_approval$',
                r'/program/hide_aggregate$',
            )
            son = to_son(submission)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get a list.'''
        term = self.get_argument('term', '')
        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        approval = self.get_argument('approval', '')
        tracking_id = self.get_argument('trackingId', '')
        deleted = self.get_argument('deleted', '')

        organisation_id = self.get_argument('organisationId', '')
        if self.current_user.role in {'clerk', 'org_admin'}:
            if organisation_id == '':
                organisation_id = str(self.organisation.id)
            elif organisation_id != str(self.organisation.id):
                raise errors.AuthzError(
                    "You can't view another organisation's submissions")

        with model.session_scope() as session:
            query = session.query(model.Submission)

            if term != '':
                query = query.filter(
                    model.Submission.title.ilike(r'%{}%'.format(term)))

            if program_id != '':
                query = query.filter_by(program_id=program_id)

            if survey_id != '':
                query = query.filter_by(survey_id=survey_id)

            if approval != '':
                approval_set = self.approval_set(approval)
                log.debug('Approval set: %s', approval_set)
                query = query.filter(
                    model.Submission.approval.in_(approval_set))

            if organisation_id != '':
                query = query.filter_by(organisation_id=organisation_id)

            if tracking_id != '':
                query = query.join(model.Program)
                query = query.filter(model.Program.tracking_id == tracking_id)

            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Submission.deleted == deleted)

            query = query.order_by(model.Submission.created.desc())
            query = self.paginate(query)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/name$',
                r'/approval$',
                r'/created$',
                r'/deleted$',
                r'/program/tracking_id$',
                r'^/[0-9]+/error$',
                # Descend
                r'/[0-9]+$',
                r'/organisation$',
                r'/survey$',
                r'/program$'
            )
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, submission_id):
        '''Create new.'''
        if submission_id != '':
            raise errors.MethodError("Can't use POST for existing object")

        program_id = self.get_argument('programId', '')
        if program_id == '':
            raise errors.ModelError("Program ID is required")

        survey_id = self.get_argument('surveyId', '')
        if survey_id == '':
            raise errors.ModelError("Survey ID is required")

        organisation_id = self.get_argument('organisationId', '')
        if organisation_id == '':
            raise errors.ModelError("Organisation ID is required")

        # Source submission ID
        duplicate_id = self.get_argument('duplicateId', '')

        fill_random = truthy(self.get_argument('fillRandom', ''))

        if organisation_id != str(self.organisation.id):
            self.check_privillege('consultant')

        try:
            with model.session_scope() as session:
                self._check_open(program_id, survey_id, organisation_id, session)

                submission = model.Submission(
                    program_id=program_id, survey_id=survey_id,
                    organisation_id=organisation_id, approval='draft')
                self._update(submission, self.request_son)
                session.add(submission)
                session.flush()
                submission_id = str(submission.id)

                if duplicate_id != '':
                    yield SubmissionHandler.executor.submit(
                        self.duplicate, submission, duplicate_id, session)

                elif fill_random:
                    self.check_privillege('author')
                    yield SubmissionHandler.executor.submit(
                        self.fill_random, submission, session)

                act = Activities(session)
                act.record(self.current_user, submission, ['create'])
                if not act.has_subscription(self.current_user, submission):
                    act.subscribe(self.current_user, submission.organisation)
                    self.reason("Subscribed to organisation")

        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(submission_id)

    def _check_open(self, program_id, survey_id, organisation_id, session):
        survey = (session.query(model.Survey)
            .get((survey_id, program_id)))
        if not survey:
            raise errors.ModelError("No such survey")
        if survey.deleted:
            raise errors.ModelError("That survey has been deleted")
        if survey.program.deleted:
            raise errors.ModelError("That program has been deleted")

        purchased_survey = (session.query(model.PurchasedSurvey)
            .filter_by(program_id=program_id,
                       survey_id=survey_id,
                       organisation_id=organisation_id)
            .first())
        if not purchased_survey:
            raise errors.ModelError(
                "Survey is not open: it needs to be purchased")

    def duplicate(self, submission, duplicate_id, session):
        s_submission = session.query(model.Submission).get(duplicate_id)
        if s_submission is None:
            raise errors.MissingDocError(
                "Source submission (for duplication) not found")

        if str(s_submission.organisation_id) != str(submission.organisation_id):
            raise errors.ModelError(
                "Can't duplicate a submission across two organisations: "
                "'%s' and '%s'" % (
                    s_submission.organisation.name,
                    submission.organisation.name))

        survey_id = str(submission.survey.id)
        measure_ids = {
            str(qm.measure_id)
            for qm in submission.survey.ordered_qnode_measures}

        qnode_ids = {str(q.id) for q in  submission.survey.ordered_qnodes}

        s_rnodes = (session.query(model.ResponseNode)
                .filter_by(submission_id=s_submission.id)
                .filter(model.ResponseNode.qnode_id.in_(qnode_ids))
                .all())

        for rnode in s_rnodes:
            if str(rnode.qnode_id) not in qnode_ids:
                continue

            # Duplicate
            session.expunge(rnode)
            make_transient(rnode)

            # Customise
            rnode.program = submission.program
            rnode.submission = submission
            session.add(rnode)
            session.flush()
            # No need to flush because no dependencies

        for response in s_submission.responses:
            if str(response.measure_id) not in measure_ids:
                continue

            attachments = list(response.attachments)

            # Fetch lazy-loaded fields
            response.comment

            # Duplicate
            session.expunge(response)
            make_transient(response)

            # Customise
            response.submission_id = submission.id
            response.program_id = submission.program_id
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
        calculator = Calculator.scoring(submission)
        calculator.mark_entire_survey_dirty(submission.survey)
        calculator.execute()

    def fill_random(self, submission, session):
        '''
        Fill the rnodes with random scores for testing purposes.
        '''

        def lerp(a, b, fac):
            return ((b - a) * fac) + a

        def new_bias(bias, hold=0.8):
            return lerp(random.random(), bias, hold)

        def visit_qnode(qnode, bias):
            rnode = qnode.get_rnode(submission)
            if not rnode:
                rnode = model.ResponseNode(
                    program=submission.program, submission=submission,
                    qnode=qnode)
                session.add(rnode)
            score = 0
            for child in qnode.children:
                score += visit_qnode(child, new_bias(bias))
            for qnode_measure in qnode.qnode_measures:
                score += new_bias(bias) * qnode_measure.measure.weight
            rnode.score = score
            return score

        user = session.query(model.AppUser).get(str(self.current_user.id))

        for i, qnode in enumerate(submission.survey.qnodes):
            random.seed(i)
            bias = random.random()
            random.seed()
            visit_qnode(qnode, new_bias(bias, hold=0.2))

    @tornado.web.authenticated
    def put(self, submission_id):
        '''Update existing.'''
        if submission_id == '':
            raise errors.MethodError("Submission ID required")

        approval = self.get_argument('approval', '')

        try:
            with model.session_scope() as session:
                submission = session.query(model.Submission)\
                    .get(submission_id)
                if submission is None:
                    raise errors.ModelError("No such submission")
                self._check_modify(submission)

                verbs = []
                if approval != '':
                    self._check_approval(session, submission, approval)
                    if approval != submission.approval:
                        verbs.append('state')
                    self._set_approval(submission, approval)
                self._update(submission, self.request_son)
                if session.is_modified(submission):
                    verbs.append('update')

                if submission.deleted:
                    submission.deleted = False
                    verbs.append('undelete')

                act = Activities(session)
                act.record(self.current_user, submission, verbs)
                if not act.has_subscription(self.current_user, submission):
                    act.subscribe(self.current_user, submission.organisation)
                    self.reason("Subscribed to organisation")

        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(submission_id)

    @tornado.web.authenticated
    def delete(self, submission_id):
        if submission_id == '':
            raise errors.MethodError("Submission ID required")

        try:
            with model.session_scope() as session:
                submission = session.query(model.Submission)\
                    .get(submission_id)
                if submission is None:
                    raise errors.ModelError("No such submission")
                self._check_delete(submission)

                act = Activities(session)
                if not submission.deleted:
                    act.record(self.current_user, submission, ['delete'])
                if not act.has_subscription(self.current_user, submission):
                    act.subscribe(self.current_user, submission.organisation)
                    self.reason("Subscribed to organisation")

                submission.deleted = True
        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError("This submission is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise errors.MissingDocError("No such submission")

        self.finish()

    def _check_delete(self, submission):
        if submission.organisation.id != self.organisation.id:
            self.check_privillege('admin')

    def _check_modify(self, submission):
        if submission.organisation.id != self.organisation.id:
            self.check_privillege('consultant')

    def _check_approval(self, session, submission, approval):
        approval_set = self.approval_set(approval)

        n_relevant_responses = (session.query(model.Response)
                 .filter(model.Response.submission_id == submission.id,
                         model.Response.approval.in_(approval_set))
                 .count())
        n_measures = (session.query(model.QnodeMeasure.measure_id)
                .join(model.QuestionNode)
                .filter(model.QuestionNode.survey_id ==
                            submission.survey_id,
                        model.QuestionNode.program_id == submission.program_id,
                        model.QnodeMeasure.program_id == submission.program_id,
                        model.QnodeMeasure.qnode_id == model.QuestionNode.id)
                .distinct()
                .count())

        if n_relevant_responses < n_measures:
            raise errors.ModelError(
                "%d of %d responses are incomplete" %
                (n_measures - n_relevant_responses, n_measures))

    def approval_set(self, minimum):
        order = ['draft', 'final', 'reviewed', 'approved']
        return order[order.index(minimum):]

    def _set_approval(self, submission, approval):
        if self.current_user.role == 'org_admin':
            if approval not in {'draft', 'final'}:
                raise errors.AuthzError(
                    "You can't mark this submission as %s." % approval)
        elif self.current_user.role == 'consultant':
            if approval not in {'draft', 'final', 'reviewed'}:
                raise errors.AuthzError(
                    "You can't mark this submission as %s." % approval)
        elif self.has_privillege('authority'):
            pass
        else:
            raise errors.AuthzError(
                "You can't mark this submission as %s." % approval)
        submission.approval = approval

    def _update(self, submission, son):
        update = updater(submission, error_factory=errors.ModelError)
        update('title', son)

        if son["created"]:
            try:
                created = datetime.datetime.fromtimestamp(son['created'])
            except TypeError as e:
                raise errors.ModelError("Invalid date")
            update('created', {"created": created})
