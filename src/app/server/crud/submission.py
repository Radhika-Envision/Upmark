from concurrent.futures import ThreadPoolExecutor
import datetime
import logging

from tornado import gen
from tornado.escape import json_encode
import tornado.web
from sqlalchemy.orm.session import make_transient

from activity import Activities
import base_handler
import errors
import model
from score import Calculator
from utils import ToSon, truthy, updater
from .approval import APPROVAL_STATES
from surveygroup_actions import filter_surveygroups
from response_type import ResponseTypeError
import os
log = logging.getLogger('app.crud.submission')

MAX_WORKERS = 4


class SubmissionHandler(base_handler.Paginate, base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, submission_id):
        if submission_id == '':
            self.query()
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            submission = session.query(model.Submission).get(submission_id)

            if not submission:
                raise errors.MissingDocError("No such submission")

            policy = user_session.policy.derive({
                'org': submission.organisation,
                'surveygroups': submission.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_view')

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
            # menu for export asset management show if asset management template exist  src/app/client/report
            # local path "src/app/client/report/" + submission.survey.title + ' Template.xlsx"
            #templateFile = "src/app/client/report/" + submission.survey.title + ' Template.xlsx'
            # local path "app/client/report/" + submission.survey.title + ' Template.xlsx"
            templateFile = "app/client/report/" + submission.survey.title + ' Template.xlsx'
            if os.path.isfile(templateFile):
                son["showCreateAssetReport"] = True
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

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            if user_session.user.role in {'clerk', 'org_admin'}:
                if not organisation_id:
                    organisation_id = user_session.org.id

            if organisation_id:
                org = session.query(model.Organisation).get(organisation_id)
                if not org:
                    raise errors.MissingDocError("No such organisation")

                policy = user_session.policy.derive({
                    'org': org,
                    'surveygroups': org.surveygroups,
                })
                policy.verify('surveygroup_interact')
                policy.verify('submission_browse')

            else:
                policy = user_session.policy.derive({})
                policy.verify('submission_browse_any')

            query = session.query(model.Submission)

            if term:
                query = query.filter(
                    model.Submission.title.ilike(r'%{}%'.format(term)))

            if program_id:
                query = query.filter(model.Submission.program_id == program_id)

            if survey_id:
                query = query.filter(model.Submission.survey_id == survey_id)

            if approval:
                approval_set = self.approval_set(approval)
                log.debug('Approval set: %s', approval_set)
                query = query.filter(
                    model.Submission.approval.in_(approval_set))

            if organisation_id:
                query = query.filter(
                    model.Submission.organisation_id == organisation_id)

            if tracking_id:
                query = query.join(model.Program)
                query = query.filter(model.Program.tracking_id == tracking_id)

            if deleted:
                deleted = truthy(deleted)
                query = query.filter(model.Submission.deleted == deleted)

            if not policy.check('surveygroup_interact_all'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [model.Organisation, model.Program], [
                        model.organisation_surveygroup,
                        model.program_surveygroup])

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
        if submission_id:
            raise errors.MethodError("Can't use POST for existing object")

        program_id = self.get_argument('programId', '')
        if not program_id:
            raise errors.ModelError("Program ID is required")

        survey_id = self.get_argument('surveyId', '')
        if not survey_id:
            raise errors.ModelError("Survey ID is required")

        organisation_id = self.get_argument('organisationId', '')
        if not organisation_id:
            raise errors.ModelError("Organisation ID is required")

        # Source submission ID
        duplicate_id = self.get_argument('duplicateId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.ModelError("No such organisation")

            survey = session.query(model.Survey).get((survey_id, program_id))
            if not survey:
                raise errors.ModelError("No such survey")

            if duplicate_id:
                source_submission = (
                    session.query(model.Submission)
                    .get(duplicate_id))
                if not source_submission:
                    raise errors.MissingDocError(
                        "Source submission (for duplication) not found")
                if source_submission.organisation != org:
                    raise errors.ModelError(
                        "Can't duplicate a submission across two "
                        "organisations: '%s' and '%s'" % (
                            source_submission.organisation.name,
                            org.name))
            else:
                source_submission = None

            submission = model.Submission(
                program=survey.program, survey=survey,
                organisation=org, approval='draft')
            self._update(submission, self.request_son)
            session.add(submission)

            surveygroups = submission.surveygroups
            if source_submission:
                surveygroups &= source_submission.surveygroups

            policy = user_session.policy.derive({
                'org': org,
                'survey': survey,
                'surveygroups': surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_add')

            session.flush()
            submission_id = str(submission.id)

            if source_submission:
                yield SubmissionHandler.executor.submit(
                    self.duplicate, submission, source_submission, session)

            act = Activities(session)
            act.record(user_session.user, submission, ['create'])
            act.ensure_subscription(
                user_session.user, submission, submission.organisation,
                self.reason)

        self.get(submission_id)

    def duplicate(self, submission, s_submission, session):
        measure_ids = {
            str(qm.measure_id)
            for qm in submission.survey.ordered_qnode_measures}

        qnode_ids = {str(q.id) for q in submission.survey.ordered_qnodes}

        s_rnodes = (
            session.query(model.ResponseNode)
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
            response.survey_id = submission.survey_id
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

    @tornado.web.authenticated
    def put(self, submission_id):
        '''Update existing.'''
        if submission_id == '':
            raise errors.MethodError("Submission ID required")

        approval = self.get_argument('approval', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            submission = session.query(model.Submission).get(submission_id)
            if not submission:
                raise errors.MissingDocError("No such submission")

            policy = user_session.policy.derive({
                'org': submission.organisation,
                'approval': approval,
                'surveygroups': submission.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_edit')

            current_level = 0
            verbs = []
            if approval:
                self.check_approval_down_one(session, submission, approval)
                current_level = APPROVAL_STATES.index(submission.approval) 
                if approval != submission.approval:
                    verbs.append('state')
                submission.approval = approval
            self._update(submission, self.request_son)
            if session.is_modified(submission):
                verbs.append('update')
            
            # update measures approval state, when save edited submission no approval, so here should not 
            if approval!='':
                approval_level = APPROVAL_STATES.index(approval) 
                if 'state' in verbs and approval_level > current_level:    
                    approval_level=approval_level-1
                    responses = (
                        session.query(model.Response)
                        .filter(model.Response.submission_id == submission.id,
                         model.Response.approval == APPROVAL_STATES[approval_level])
                    )
                    for response in responses:
                        # update = updater(response, error_factory=errors.ModelError)
                        # update('title', son)
                        response.approval = approval
                        try:
                            calculator = Calculator.scoring(submission)
                            calculator.mark_measure_dirty(response.qnode_measure)
                            calculator.execute()
                        except ResponseTypeError as e:
                            raise errors.ModelError(str(e))


                        act = Activities(session)
                        act.record(user_session.user, response, verbs)
                        act.ensure_subscription(
                            user_session.user, response, response.submission,
                            self.reason)

            if submission.deleted:
                submission.deleted = False
                verbs.append('undelete')

            act = Activities(session)
            act.record(user_session.user, submission, verbs)
            act.ensure_subscription(
                user_session.user, submission, submission.organisation,
                self.reason)

        self.get(submission_id)

    @tornado.web.authenticated
    def delete(self, submission_id):
        if submission_id == '':
            raise errors.MethodError("Submission ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            submission = (
                session.query(model.Submission)
                .get(submission_id))
            if not submission:
                raise errors.MissingDocError("No such submission")

            policy = user_session.policy.derive({
                'org': submission.organisation,
                'surveygroups': submission.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_del')

            act = Activities(session)
            if not submission.deleted:
                act.record(user_session.user, submission, ['delete'])
            act.ensure_subscription(
                user_session.user, submission, submission.organisation,
                self.reason)

            submission.deleted = True

        self.finish()

    # for submeasure version
    def check_approval_down_one(self, session, submission, approval):
        approval_set = self.approval_set_down_one(approval)

        n_relevant_responses = (
            session.query(model.Response)
            .filter(model.Response.submission_id == submission.id,
                    model.Response.approval.in_(approval_set))
            .count())
        n_measures = (
            session.query(model.QnodeMeasure.measure_id)
            .join(model.QuestionNode)
            .filter(model.QuestionNode.survey_id == submission.survey_id,
                    model.QuestionNode.program_id == submission.program_id,
                    model.QnodeMeasure.program_id == submission.program_id,
                    model.QnodeMeasure.qnode_id == model.QuestionNode.id,
                    model.QuestionNode.deleted == False)
            .distinct()
            .count())

        if n_relevant_responses < n_measures:
            raise errors.ModelError(
                "%d of %d responses are incomplete" %
                (n_measures - n_relevant_responses, n_measures))

    # for submeasure version: get last one level APPROVAL_STATES
    def approval_set_down_one(self, minimum):
        level=APPROVAL_STATES.index(minimum)
        if level>0:
            level=level-1
        return APPROVAL_STATES[level:]

    # for not submeasure version
    def check_approval(self, session, submission, approval):
        approval_set = self.approval_set(approval)

        n_relevant_responses = (
            session.query(model.Response)
            .filter(model.Response.submission_id == submission.id,
                    model.Response.approval.in_(approval_set))
            .count())
        n_measures = (
            session.query(model.QnodeMeasure.measure_id)
            .join(model.QuestionNode)
            .filter(model.QuestionNode.survey_id == submission.survey_id,
                    model.QuestionNode.program_id == submission.program_id,
                    model.QnodeMeasure.program_id == submission.program_id,
                    model.QnodeMeasure.qnode_id == model.QuestionNode.id,
                    model.QuestionNode.deleted == False)
            .distinct()
            .count())

        if n_relevant_responses < n_measures:
            raise errors.ModelError(
                "%d of %d responses are incomplete" %
                (n_measures - n_relevant_responses, n_measures))
    # for not submeasure version
    def approval_set(self, minimum):
        return APPROVAL_STATES[APPROVAL_STATES.index(minimum):]

    def _update(self, submission, son):
        update = updater(submission, error_factory=errors.ModelError)
        update('title', son)

        if son["created"]:
            try:
                created = datetime.datetime.fromtimestamp(son['created'])
            except TypeError as e:
                raise errors.ModelError("Invalid date")
            update('created', {"created": created})
