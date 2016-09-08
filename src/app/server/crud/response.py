import datetime
import logging
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import object_session

from activity import Activities
import handlers
import model
from response_type import ResponseTypeError
from score import Calculator
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.response')


STATES = ['draft', 'final', 'reviewed', 'approved']


def check_approval_change(role, submission, approval):
    '''
    Check whether a user can set the state of a response, given the current
    state of the submission.
    '''
    if STATES.index(submission.approval) > STATES.index(approval):
        raise handlers.ModelError(
            "The submission has a state of '%s'."
            % submission.approval)

    if role in {'org_admin', 'clerk'}:
        if approval not in {'draft', 'final'}:
            raise handlers.AuthzError(
                "You can't mark this as %s." % approval)
    elif role == 'consultant':
        if approval not in {'draft', 'final', 'reviewed'}:
            raise handlers.AuthzError(
                "You can't mark this as %s." % approval)
    elif model.has_privillege(role, 'authority'):
        pass
    else:
        raise handlers.AuthzError(
            "You can't mark this as %s." % approval)


def check_modify(role, response):
    '''
    Check whether a user can modify a response in its current state.
    '''
    if response.approval in {'draft', 'final'}:
        pass
    elif response.approval == 'reviewed':
        if not model.has_privillege(role, 'consultant'):
            raise handlers.AuthzError(
                "This response has already been reviewed")
    else:
        if not model.has_privillege(role, 'authority'):
            raise handlers.AuthzError(
                "This response has already been approved")


class ResponseHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, submission_id, measure_id):
        '''Get a single response.'''

        if measure_id == '':
            self.query(submission_id)
            return

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            response = (session.query(model.Response)
                    .filter_by(submission_id=submission_id,
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

            self._check_authz(response.submission)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/name$',
                # Fields to match from only the root object
                r'^/submission_id$',
                r'^/measure_id$',
                r'<^/comment$',
                r'^/response_parts.*$',
                r'^/not_relevant$',
                r'^/attachments$',
                r'^/audit_reason$',
                r'^/approval$',
                r'^/version$',
                r'^/modified$',
                r'^/quality$',
                # Descend
                r'/parent$',
                r'/measure$',
                r'/submission$',
                r'/user$',
            )
            to_son.exclude(
                # The IDs of rnodes and responses are not part of the API
                r'^/id$',
                r'/parent/id$'
            )
            if response_history is None:
                son = to_son(response)
            else:
                son = to_son(response_history)
                submission = (session.query(model.Submission)
                        .filter_by(id=response_history.submission_id)
                        .first())
                measure = (session.query(model.Measure)
                        .filter_by(id=response_history.measure_id,
                                   program_id=submission.program_id)
                        .first())
                parent = (measure.get_parent(submission.survey_id)
                        .get_rnode(submission_id))
                user = (session.query(model.AppUser)
                        .filter_by(id=response_history.user_id)
                        .first())
                dummy_relations = {
                    'parent': parent,
                    'measure': measure,
                    'submission': submission,
                    'user': user
                }
                son.update(to_son(dummy_relations))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, submission_id):
        '''Get a list.'''
        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == '':
            raise handlers.ModelError("qnode ID required")

        with model.session_scope() as session:
            submission = (session.query(model.Submission)
                .filter_by(id=submission_id)
                .first())

            if submission is None:
                raise handlers.MissingDocError("No such submission")
            self._check_authz(submission)

            rnode = (session.query(model.ResponseNode)
                .filter_by(submission_id=submission_id,
                           qnode_id=qnode_id)
                .first())

            if rnode is None:
                responses = []
            else:
                responses = rnode.responses

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/approval$',
                r'/modified$',
                r'/not_relevant$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/measure$',
                # The IDs of rnodes and responses are not part of the API
                r'!^/[0-9]+/id$',
            )
            if self.current_user.role == 'clerk':
                to_son.exclude(r'/score$')
            sons = to_son(responses)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # There is no POST, because responses are accessed by measure + submission
    # instead of by their own ID.

    @tornado.web.authenticated
    def put(self, submission_id, measure_id):
        '''Save (create or update).'''

        approval = self.get_argument('approval', '')

        try:
            with model.session_scope(version=True) as session:
                submission = (session.query(model.Submission)
                    .get(submission_id))
                if submission is None:
                    raise handlers.MissingDocError("No such submission")

                self._check_authz(submission)

                query = (session.query(model.Response).filter_by(
                     submission_id=submission_id, measure_id=measure_id))
                response = query.first()

                verbs = []
                if response is None:
                    measure = (session.query(model.Measure)
                        .get((measure_id, submission.program.id)))
                    if measure is None:
                        raise handlers.MissingDocError("No such measure")
                    response = model.Response(
                        submission_id=submission_id,
                        measure_id=measure_id,
                        program_id=submission.program.id,
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
                    check_approval_change(
                        self.current_user.role, submission, approval)

                    if approval != response.approval:
                        verbs.append('state')

                self._update(response, self.request_son, approval)
                if not session.is_modified(response) and 'update' in verbs:
                    verbs.remove('update')
                check_modify(self.current_user.role, response)
                session.flush()

                # Prevent creating a second version during following operations
                response.version_on_update = False

                try:
                    calculator = Calculator.scoring(submission)
                    calculator.mark_measure_dirty(response.qnode_measure)
                    calculator.execute()
                except ResponseTypeError as e:
                    raise handlers.ModelError(str(e))

                act = Activities(session)
                act.record(self.current_user, response, verbs)
                if not act.has_subscription(self.current_user, response):
                    act.subscribe(self.current_user, response.submission)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(submission_id, measure_id)

    def _check_authz(self, submission):
        if not self.has_privillege('consultant'):
            if submission.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")

    def _update(self, response, son, approval):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(response)
        update('comment', son, sanitise=True)
        update('not_relevant', son)
        update('response_parts', son)
        update('quality', son)

        extras = {
            'modified': datetime.datetime.utcnow(),
            'user_id': str(self.current_user.id),
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
    def get(self, submission_id, measure_id):
        '''Get a list of versions of a response.'''
        with model.session_scope() as session:
            # Current version
            versions = (session.query(model.Response)
                .filter_by(submission_id=submission_id,
                           measure_id=measure_id)
                .all())

            # Other versions
            query = (session.query(model.ResponseHistory)
                .filter_by(submission_id=submission_id,
                           measure_id=measure_id)
                .order_by(model.ResponseHistory.version.desc()))
            query = self.paginate(query)

            versions += query.all()

            # Important! If you're going to include the comment field here, make
            # sure it is cleaned first to prevent XSS attacks.
            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/approval$',
                r'/version$',
                r'/modified$',
                # Descend
                r'/[0-9]+$',
                r'/user$',
                r'/organisation$',
                # The IDs of rnodes and responses are not part of the API
                r'!^/[0-9]+/id$',
            )
            sons = to_son(versions)

            for son, version in zip(sons, versions):
                user = session.query(model.AppUser).get(version.user_id)
                if user is not None:
                    son['user'] = to_son(user)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
