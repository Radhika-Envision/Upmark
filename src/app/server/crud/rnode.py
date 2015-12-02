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

from response_type import ResponseTypeError
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.rnode')


class ResponseNodeHandler(handlers.BaseHandler):

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
    def put(self, assessment_id, qnode_id):
        '''Save (create or update).'''

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

                self._update(rnode, self.request_son)
                session.flush()

                try:
                    rnode.update_stats_ancestors()
                except (model.ModelError, ResponseTypeError) as e:
                    raise handlers.ModelError(str(e))

                act = crud.activity.Activities(session)
                act.record(self.current_user, rnode, ['update'])
                if not act.has_subscription(self.current_user, rnode):
                    act.subscribe(self.current_user, rnode.assessment)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id, qnode_id)

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
