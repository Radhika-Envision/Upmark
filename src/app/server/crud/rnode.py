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
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from activity import Activities
import crud.response
import crud.program
import handlers
import model
from response_type import ResponseTypeError
from score import Calculator
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.rnode')

MAX_WORKERS = 4


class ResponseNodeHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, submission_id, qnode_id):
        if qnode_id == '':
            self.query(submission_id)
            return

        with model.session_scope() as session:
            rnode = (session.query(model.ResponseNode)
                .get((submission_id, qnode_id)))

            if rnode is None:
                # Create an empty one, and roll back later (because GET
                # shouldn't modify anything).
                qnode, submission = (session.query(
                        model.QuestionNode, model.Submission)
                    .join(model.Program)
                    .join(model.Submission)
                    .filter(model.QuestionNode.id == qnode_id,
                            model.Submission.id == submission_id)
                    .first())
                if qnode is None:
                    raise handlers.MissingDocError("No such category")
                rnode = model.ResponseNode(
                    qnode=qnode,
                    qnode_id=qnode_id,
                    submission=submission,
                    submission_id=submission_id,
                    score=0,
                    n_draft=0,
                    n_final=0,
                    n_reviewed=0,
                    n_approved=0,
                    n_not_relevant=0)

            self._check_authz(rnode.submission)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/score$',
                r'/total_weight$',
                r'/submission_id$',
                r'/qnode_id$',
                r'/n_draft$',
                r'/n_final$',
                r'/n_reviewed$',
                r'/n_approved$',
                r'/n_measures$',
                r'/n_not_relevant$',
                r'/(max_)?importance$',
                r'/(max_)?urgency$',
                r'^/error$',
                # Descend into nested objects
                r'/qnode$',
                # The IDs of rnodes and responses are not part of the API
                r'!^/id$',
            )
            if self.current_user.role == 'clerk':
                to_son.exclude(
                    r'/score$',
                    r'/total_weight$',
                )

            son = to_son(rnode)

            # Don't commit empty rnode here: GET should not change anything!
            session.rollback()

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, submission_id):
        '''Get a list.'''
        parent_id = self.get_argument('parentId', '')
        root = self.get_argument('root', None)

        if root is not None and parent_id != '':
            raise handlers.ModelError(
                "Can't specify parent ID when requesting roots")
        if root is None and parent_id == '':
            raise handlers.ModelError(
                "'root' or parent ID required")

        with model.session_scope() as session:
            submission = (session.query(model.Submission)
                .get((submission_id,)))

            if submission is None:
                raise handlers.MissingDocError("No such submission")
            self._check_authz(submission)

            if root is not None:
                children = submission.rnodes
            else:
                rnode = (session.query(model.ResponseNode)
                    .get((submission_id, parent_id)))
                if rnode is None:
                    # Rnodes get created from the bottom of the tree up, so if
                    # the parent doesn't exist, its children shouldn't either.
                    children = []
                else:
                    children = rnode.children

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/total_weight$',
                r'/n_draft$',
                r'/n_final$',
                r'/n_reviewed$',
                r'/n_approved$',
                r'/n_measures$',
                r'/n_not_relevant$',
                r'/max_importance$',
                r'/max_urgency$',
                r'^/[0-9]+/error$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/qnode$',
                # The IDs of rnodes and responses are not part of the API
                r'!^/[0-9]+/id$',
            )
            if self.current_user.role == 'clerk':
                to_son.exclude(
                    r'/score$',
                    r'/total_weight$'
                )
            sons = to_son(children)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # There is no POST, because rnodes are accessed by qnode + submission
    # instead of by their own ID.

    @tornado.web.authenticated
    @gen.coroutine
    def put(self, submission_id, qnode_id):
        '''Save (create or update).'''

        approval = self.get_argument('approval', '')
        relevance = self.get_argument('relevance', '')

        try:
            with model.session_scope() as session:
                submission = (session.query(model.Submission)
                    .get(submission_id))
                if submission is None:
                    raise handlers.MissingDocError("No such submission")

                self._check_authz(submission)

                rnode = (session.query(model.ResponseNode)
                    .get((submission_id, qnode_id)))

                verbs = []

                if rnode is None:
                    qnode = (session.query(model.QuestionNode)
                        .get((qnode_id, submission.program.id)))
                    if qnode is None:
                        raise handlers.MissingDocError("No such question node")
                    rnode = qnode.get_rnode(submission, create=True)

                importance = self.request_son.get('importance')
                if importance is not None:
                    if importance <= 0:
                        self.request_son['importance'] = None
                    elif importance > 5:
                        self.request_son['importance'] = 5
                urgency = self.request_son.get('urgency')
                if urgency is not None:
                    if urgency <= 0:
                        self.request_son['urgency'] = None
                    elif urgency > 5:
                        self.request_son['urgency'] = 5
                self._update(rnode, self.request_son)
                if session.is_modified(rnode):
                    verbs.append('update')
                session.flush()

                if approval != '':
                    yield self.set_approval(session, rnode, approval)
                    verbs.append('state')
                if relevance != '':
                    yield self.set_relevance(session, rnode, relevance)
                    verbs.append('update')

                try:
                    calculator = Calculator.scoring(submission)
                    calculator.mark_qnode_dirty(rnode.qnode)
                    calculator.execute()
                except ResponseTypeError as e:
                    raise handlers.ModelError(str(e))

                act = Activities(session)
                act.record(self.current_user, rnode, verbs)
                if not act.has_subscription(self.current_user, rnode):
                    act.subscribe(self.current_user, rnode.submission)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(submission_id, qnode_id)

    @run_on_executor
    def set_relevance(self, session, rnode, relevance):
        not_relevant = relevance == 'NOT_RELEVANT'
        if not_relevant:
            missing = self.get_argument('missing', '')
        else:
            # When marking responses as not NA, just ignore missing responses.
            # It's not possible to create new ones because a non-NA response
            # must have its response parts filled in.
            missing = 'IGNORE'

        submission = rnode.submission
        changed = failed = created = 0

        calculator = Calculator.scoring(submission)
        for response, is_new in self.walk_responses(session, rnode, missing):
            try:
                crud.response.check_modify(self.current_user.role, response)
            except (handlers.AuthzError, handlers.ModelError) as e:
                err = ("Response %s: %s You might need to downgrade the "
                    "response's approval status. You can use the bulk "
                    "approval tool for this.".format(
                        response.qnode_measure.get_path(), e))
                if isinstance(e, handlers.AuthzError):
                    raise handlers.AuthzError(err)
                else:
                    raise handlers.ModelError(err)
            if not_relevant:
                response.not_relevant = True
                if is_new:
                    # Try to set to current submission approval state, IF user
                    # is allowed
                    try:
                        crud.response.check_approval_change(
                            self.current_user.role, submission, submission.approval)
                    except (handlers.AuthzError, handlers.ModelError) as e:
                        err = ("Response %s: %s You might "
                            "need to downgrade the submission's approval "
                            "status.".format(
                                response.qnode_measure.get_path(),
                                e))
                        if isinstance(e, handlers.AuthzError):
                            raise handlers.AuthzError(err)
                        else:
                            raise handlers.ModelError(err)
                    response.approval = submission.approval
                    response.comment = "*Marked Not Relevant as a bulk action " \
                        "(was previously empty)*"
                    created += 1
                else:
                    changed += 1
            else:
                response.not_relevant = False
                changed += 1
            calculator.mark_measure_dirty(response.qnode_measure)

        calculator.execute()

        if created:
            self.reason("Created %d" % created)
        if changed:
            self.reason("Changed %d" % changed)
        if failed:
            self.reason(
                "%d measures could not be changed, because a relevant "
                " response must have valid data." % failed)

        if created == changed == failed == 0:
            self.reason("No changes to relevance")

    @run_on_executor
    def set_approval(self, session, rnode, approval):
        crud.response.check_approval_change(
            self.current_user.role, rnode.submission, approval)

        promote = self.get_arguments('promote')
        missing = self.get_argument('missing', '')

        submission = rnode.submission
        promoted = demoted = created = 0

        calculator = Calculator.scoring(submission)
        for response, is_new in self.walk_responses(session, rnode, missing):
            if is_new:
                response.not_relevant = True
                response.approval = approval
                response.comment = "*Marked Not Relevant by bulk approval " \
                    "process (was previously empty)*"
                created += 1
            else:
                i1 = crud.response.STATES.index(response.approval)
                i2 = crud.response.STATES.index(approval)
                if i1 < i2 and 'PROMOTE' in promote:
                    response.approval = approval
                    response.modified = func.now()
                    promoted += 1
                elif i1 > i2 and 'DEMOTE' in promote:
                    response.approval = approval
                    response.modified = func.now()
                    demoted += 1
            calculator.mark_measure_dirty(response.qnode_measure)

        calculator.execute()

        if created:
            self.reason("Created %d (NA)" % created)
        if demoted:
            self.reason("Demoted %d" % demoted)
        if promoted:
            self.reason("Promoted %d" % promoted)

        if created == promoted == demoted == 0:
            self.reason("No changes to approval status")

    def walk_responses(self, session, rnode, missing):
        for qnode_measure in rnode.qnode.ordered_qnode_measures:
            response = qnode_measure.get_response(rnode.submission)
            if not response:
                if missing != 'CREATE':
                    continue
                response = model.Response(
                    user_id=self.current_user.id,
                    submission=rnode.submission,
                    qnode_measure=qnode_measure)
                response.modified = func.now()
                session.add(response)
                created = True
            else:
                created = False
            yield response, created

    def _check_authz(self, submission):
        if not self.has_privillege('consultant'):
            if submission.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't view another organisation's response")

    def _update(self, rnode, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(rnode)
        update('importance', son)
        update('urgency', son)
