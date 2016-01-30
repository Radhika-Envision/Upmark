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
import crud.survey
import handlers
import model
from response_type import ResponseTypeError
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.rnode')

MAX_WORKERS = 4


class ResponseNodeHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, assessment_id, qnode_id):
        if qnode_id == '':
            self.query(assessment_id)
            return

        with model.session_scope() as session:
            rnode = (session.query(model.ResponseNode)
                    .filter_by(assessment_id=assessment_id,
                               qnode_id=qnode_id)
                    .first())

            if rnode is None:
                raise handlers.MissingDocError("No such response node")

            self._check_authz(rnode.assessment)

            exclude = [
                # The IDs of rnodes and responses are not part of the API
                r'^/id$',
            ]
            if self.current_user.role == 'clerk':
                exclude.append(r'/score$')
                exclude.append(r'/total_weight$')

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/total_weight$',
                r'/assessment_id$',
                r'/qnode_id$',
                r'/n_submitted$',
                r'/n_reviewed$',
                r'/n_approved$',
                r'/n_measures$',
                r'/n_not_relevant$',
                r'/not_relevant$',
                r'/(max_)?importance$',
                r'/(max_)?urgency$',
                # Descend into nested objects
                r'/qnode$',
            ], exclude=exclude)
            son = to_son(rnode)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, assessment_id):
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
            assessment = (session.query(model.Assessment)
                .filter_by(id=assessment_id)
                .first())

            if assessment is None:
                raise handlers.MissingDocError("No such submission")
            self._check_authz(assessment)

            if root is not None:
                children = assessment.rnodes
            else:
                rnode = (session.query(model.ResponseNode)
                    .filter_by(assessment_id=assessment_id,
                               qnode_id=parent_id)
                    .first())
                if rnode is None:
                    children = []
                else:
                    children = rnode.children

            exclude = [
                # The IDs of rnodes and responses are not part of the API
                r'^/[0-9]+/id$',
            ]
            if self.current_user.role == 'clerk':
                exclude.append(r'/score$')
                exclude.append(r'/total_weight$')

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/total_weight$',
                r'/n_submitted$',
                r'/n_reviewed$',
                r'/n_approved$',
                r'/n_measures$',
                r'/n_not_relevant$',
                r'/not_relevant$',
                r'/max_importance$',
                r'/max_urgency$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/qnode$',
            ], exclude=exclude)
            sons = to_son(children)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # There is no POST, because rnodes are accessed by qnode + assessment
    # instead of by their own ID.

    @tornado.web.authenticated
    @gen.coroutine
    def put(self, assessment_id, qnode_id):
        '''Save (create or update).'''

        approval = self.get_argument('approval', '')

        try:
            with model.session_scope() as session:
                assessment = (session.query(model.Assessment)
                    .get(assessment_id))
                if assessment is None:
                    raise handlers.MissingDocError("No such submission")

                self._check_authz(assessment)

                query = (session.query(model.ResponseNode).filter_by(
                     assessment_id=assessment_id, qnode_id=qnode_id))
                rnode = query.first()

                verbs = []

                if rnode is None:
                    qnode = (session.query(model.QuestionNode)
                        .get((qnode_id, assessment.survey.id)))
                    if qnode is None:
                        raise handlers.MissingDocError("No such question node")
                    rnode = model.ResponseNode(
                        assessment_id=assessment_id,
                        qnode_id=qnode_id,
                        survey_id=assessment.survey.id,
                        not_relevant=False)
                    session.add(rnode)

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

                try:
                    rnode.update_stats_ancestors()
                except (model.ModelError, ResponseTypeError) as e:
                    raise handlers.ModelError(str(e))

                act = Activities(session)
                act.record(self.current_user, rnode, verbs)
                if not act.has_subscription(self.current_user, rnode):
                    act.subscribe(self.current_user, rnode.assessment)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id, qnode_id)

    @run_on_executor
    def set_approval(self, session, rnode, approval):
        crud.response.check_approval_change(
            self.current_user.role, rnode.assessment, approval)

        promote = self.get_arguments('promote')
        missing = self.get_argument('missing', '')

        assessment = rnode.assessment
        def update_approval_descendants(qnode):
            # This is like model.ResponseNode.update_stats_descendants, but it:
            # - Creates Not Relevant responses when they don't already exist
            # - Doesn't recalculate scores (just sets approval state)
            promoted = 0
            demoted = 0
            created = 0

            rnode = qnode.get_rnode(assessment)
            if rnode and rnode.not_relevant:
                return promoted, demoted, created

            for child in qnode.children:
                p, d, c = update_approval_descendants(child)
                promoted += p
                demoted += d
                created += c

            for measure in qnode.measures:
                response = measure.get_response(assessment)
                if not response:
                    if missing == 'CREATE':
                        response = model.Response(
                            user_id=self.current_user.id,
                            assessment=assessment,
                            measure=measure,
                            survey=assessment.survey,
                            approval=approval,
                            not_relevant=True,
                            comment="*Marked Not Relevant by bulk approval "
                                    "process (was previously empty)*")
                        response.modified = func.now()
                        session.add(response)
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
            return promoted, demoted, created

        promoted, demoted, created = update_approval_descendants(rnode.qnode)
        rnode.update_stats_descendants()

        if created:
            self.reason("Created %d (NA)" % created)
        if demoted:
            self.reason("Demoted %d" % demoted)
        if promoted:
            self.reason("Promoted %d" % promoted)

        if created == promoted == demoted == 0:
            self.reason("No changes to approval status")

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't view another organisation's response")

    def _update(self, rnode, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(rnode)
        update('not_relevant', son)
        update('importance', son)
        update('urgency', son)
