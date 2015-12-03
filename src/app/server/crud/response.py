import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import object_session

import handlers
import model
import logging

from activity import Activities
from response_type import ResponseTypeError
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.response')


class ResponseHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
        '''Get a single response.'''

        if measure_id == '':
            self.query(assessment_id)
            return

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            response = (session.query(model.Response)
                    .filter_by(assessment_id=assessment_id,
                               measure_id=measure_id)
                    .first())

            if response is None:
                raise handlers.MissingDocError("No such response")

            if version != '' and version != response.version:
                try:
                    version = int(version)
                except ValueError:
                    raise handlers.ModelError("Invalid version number")
                response_history = (session.query(model.ResponseHistory)
                        .filter_by(id=response.id, version=version)
                        .first())

                if response is None:
                    raise handlers.MissingDocError("No such response version")
            else:
                response_history = None

            self._check_authz(response.assessment)

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/name$',
                # Fields to match from only the root object
                r'^/assessment_id$',
                r'^/measure_id$',
                r'^/comment$',
                r'^/response_parts.*$',
                r'^/not_relevant$',
                r'^/attachments$',
                r'^/audit_reason$',
                r'^/approval$',
                r'^/version$',
                r'^/modified$',
                # Descend
                r'/parent$',
                r'/measure$',
                r'/assessment$',
                r'/user$',
            ], exclude=[
                # The IDs of rnodes and responses are not part of the API
                r'^/id$',
                r'/parent/id$'
            ])
            if response_history is None:
                son = to_son(response)
            else:
                son = to_son(response_history)
                assessment = (session.query(model.Assessment)
                        .filter_by(id=response_history.assessment_id)
                        .first())
                measure = (session.query(model.Measure)
                        .filter_by(id=response_history.measure_id,
                                   survey_id=assessment.survey_id)
                        .first())
                parent = (measure.get_parent(assessment.hierarchy_id)
                        .get_rnode(assessment_id))
                user = (session.query(model.AppUser)
                        .filter_by(id=response_history.user_id)
                        .first())
                dummy_relations = {
                    'parent': parent,
                    'measure': measure,
                    'assessment': assessment,
                    'user': user
                }
                son.update(to_son(dummy_relations))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, assessment_id):
        '''Get a list.'''
        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == '':
            raise handlers.ModelError("qnode ID required")

        with model.session_scope() as session:
            assessment = (session.query(model.Assessment)
                .filter_by(id=assessment_id)
                .first())

            if assessment is None:
                raise handlers.MissingDocError("No such submission")
            self._check_authz(assessment)

            rnode = (session.query(model.ResponseNode)
                .filter_by(assessment_id=assessment_id,
                           qnode_id=qnode_id)
                .first())

            if rnode is None:
                responses = []
            else:
                responses = rnode.responses

            exclude = [
                # The IDs of rnodes and responses are not part of the API
                r'^/[0-9]+/id$',
            ]
            if self.current_user.role == 'clerk':
                exclude.append(r'/score$')

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/approval$',
                r'/modified$',
                r'/not_relevant$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/measure$',
            ], exclude=exclude)
            sons = to_son(responses)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # There is no POST, because responses are accessed by measure + assessment
    # instead of by their own ID.

    @tornado.web.authenticated
    def put(self, assessment_id, measure_id):
        '''Save (create or update).'''

        approval = self.get_argument('approval', '')

        try:
            with model.session_scope(version=True) as session:
                assessment = (session.query(model.Assessment)
                    .get(assessment_id))
                if assessment is None:
                    raise handlers.MissingDocError("No such submission")

                self._check_authz(assessment)

                query = (session.query(model.Response).filter_by(
                     assessment_id=assessment_id, measure_id=measure_id))
                response = query.first()

                verbs = []
                if response is None:
                    measure = (session.query(model.Measure)
                        .get((measure_id, assessment.survey.id)))
                    if measure is None:
                        raise handlers.MissingDocError("No such measure")
                    response = model.Response(
                        assessment_id=assessment_id,
                        measure_id=measure_id,
                        survey_id=assessment.survey.id,
                        approval='draft')
                    session.add(response)
                    verbs.append('create')
                else:
                    same_user = response.user.id == self.current_user.id
                    td = datetime.datetime.utcnow() - response.modified
                    hours_since_update = td.total_seconds() / 60 / 60

                    if same_user and hours_since_update < 8:
                        response.version_on_update = False

                    modified = self.request_son.get("modified", 0)
                    # Convert to int to avoid string conversion errors during
                    # JSON marshalling.
                    if int(modified) < int(response.modified.timestamp()):
                        raise handlers.ModelError(
                            "This response has changed since you loaded the"
                            " page. Please copy or remember your changes and"
                            " refresh the page.")
                    verbs.append('update')

                if approval != '':
                    self._check_approval_change(response, assessment, approval)

                    if approval != response.approval:
                        verbs.append('state')

                self._update(response, self.request_son, approval)
                if not session.is_modified(response) and 'update' in verbs:
                    verbs.remove('update')
                self._check_approval_state(response)
                session.flush()

                # Prevent creating a second version during following operations
                response.version_on_update = False

                try:
                    response.update_stats_ancestors()
                except (model.ModelError, ResponseTypeError) as e:
                    raise handlers.ModelError(str(e))

                act = Activities(session)
                act.record(self.current_user, response, verbs)
                if not act.has_subscription(self.current_user, response):
                    act.subscribe(self.current_user, response.assessment)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id, measure_id)

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")

    def _check_approval_change(self, response, assessment, approval):
        if assessment.approval == 'draft':
            pass
        elif assessment.approval == 'final':
            if not self.has_privillege('org_admin', 'consultant'):
                raise handlers.AuthzError(
                    "This submission has already been finalised")
        elif assessment.approval == 'reviewed':
            if not self.has_privillege('consultant'):
                raise handlers.AuthzError(
                    "This submission has already been reviewed")
        else:
            if not self.has_privillege('authority'):
                raise handlers.AuthzError(
                    "This submission has already been approved")

        order = ['draft', 'final', 'reviewed', 'approved']
        if order.index(assessment.approval) > order.index(approval):
            raise handlers.ModelError(
                "This response belongs to an submission with a state of '%s'."
                % assessment.approval)

        if self.current_user.role in {'org_admin', 'clerk'}:
            if approval not in {'draft', 'final'}:
                raise handlers.AuthzError(
                    "You can't mark this response as %s." % approval)
        elif self.current_user.role == 'consultant':
            if approval not in {'draft', 'final', 'reviewed'}:
                raise handlers.AuthzError(
                    "You can't mark this response as %s." % approval)
        elif self.has_privillege('authority'):
            pass
        else:
            raise handlers.AuthzError(
                "You can't mark this response as %s." % approval)

    def _check_approval_state(self, response):
        if response.approval in {'draft', 'final'}:
            pass
        elif response.approval == 'reviewed':
            if not self.has_privillege('consultant'):
                raise handlers.AuthzError(
                    "This response has already been reviewed")
        else:
            if not self.has_privillege('authority'):
                raise handlers.AuthzError(
                    "This response has already been approved")

    def _update(self, response, son, approval):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(response)
        update('comment', son)
        update('not_relevant', son)
        update('response_parts', son)

        extras = {
            'modified': datetime.datetime.utcnow(),
            'user_id': str(self.current_user.id)
        }
        if approval != '':
            extras['approval'] = approval

        update('approval', extras)
        update('audit_reason', son)

        if object_session(response).is_modified(response):
            update('modified', extras)
            update('user_id', extras)

        # Attachments are stored elsewhere.


class ResponseHistoryHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
        '''Get a list of versions of a response.'''
        with model.session_scope() as session:
            # Current version
            versions = (session.query(model.Response)
                .filter_by(assessment_id=assessment_id,
                           measure_id=measure_id)
                .all())

            # Other versions
            query = (session.query(model.ResponseHistory)
                .filter_by(assessment_id=assessment_id,
                           measure_id=measure_id)
                .order_by(model.ResponseHistory.version.desc()))
            query = self.paginate(query)

            versions += query.all()

            to_son = ToSon(include=[
                r'/id$',
                r'/name$',
                r'/approval$',
                r'/version$',
                r'/modified$',
                # Descend
                r'/[0-9]+$',
                r'/user$',
                r'/organisation$',
            ], exclude=[
                # The IDs of rnodes and responses are not part of the API
                r'^/[0-9]+/id$',
            ])
            sons = to_son(versions)

            for son, version in zip(sons, versions):
                user = session.query(model.AppUser).get(version.user_id)
                if user is not None:
                    son['user'] = to_son(user)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
