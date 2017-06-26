import datetime
import logging

from tornado.escape import json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm.session import object_session

from activity import Activities
import base_handler
import errors
import model
from response_type import ResponseTypeError
from score import Calculator
from utils import ToSon, updater


log = logging.getLogger('app.crud.response')


STATES = ['draft', 'final', 'reviewed', 'approved']


def check_approval_change(role, submission, approval):
    '''
    Check whether a user can set the state of a response, given the current
    state of the submission.
    '''
    if STATES.index(submission.approval) > STATES.index(approval):
        raise errors.ModelError(
            "The submission has a state of '%s'."
            % submission.approval)

    if role in {'org_admin', 'clerk'}:
        if approval not in {'draft', 'final'}:
            raise errors.AuthzError(
                "You can't mark this as %s." % approval)
    elif role == 'consultant':
        if approval not in {'draft', 'final', 'reviewed'}:
            raise errors.AuthzError(
                "You can't mark this as %s." % approval)
    elif model.has_privillege(role, 'authority'):
        pass
    else:
        raise errors.AuthzError(
            "You can't mark this as %s." % approval)


def check_modify(role, response):
    '''
    Check whether a user can modify a response in its current state.
    '''
    if response.approval in {'draft', 'final'}:
        pass
    elif response.approval == 'reviewed':
        if not model.has_privillege(role, 'consultant'):
            raise errors.AuthzError(
                "This response has already been reviewed")
    else:
        if not model.has_privillege(role, 'authority'):
            raise errors.AuthzError(
                "This response has already been approved")


class ResponseHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, submission_id, measure_id):
        '''Get a single response.'''

        if measure_id == '':
            self.query(submission_id)
            return

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            response = (session.query(model.Response)
                .get((submission_id, measure_id)))

            dummy = False
            if response is None:
                # Synthesise response so it can be returned. The session will be
                # rolled back to avoid actually making this change.
                submission = (session.query(model.Submission)
                    .get(submission_id))
                if not submission:
                    raise errors.MissingDocError("No such submission")

                qnode_measure = (session.query(model.QnodeMeasure)
                    .get((submission.program_id, submission.survey_id, measure_id)))
                if not qnode_measure:
                    raise errors.MissingDocError(
                        "That survey has no such measure")

                response = model.Response(
                    qnode_measure=qnode_measure,
                    submission=submission,
                    user_id=self.current_user.id,
                    comment='',
                    response_parts=[],
                    variables={},
                    not_relevant=False,
                    approval='draft',
                    modified=datetime.datetime.fromtimestamp(0),
                )
                dummy = True

            response_history = self.get_version(session, response, version)

            self._check_authz(response.submission)

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
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
                r'^/error$',
                r'^/approval$',
                r'^/version$',
                r'^/modified$',
                r'^/latest_modified$',
                r'^/quality$',
                # Descend
                r'/parent$',
                r'/measure$',
                r'/submission$',
                r'/user$',
            )

            if dummy:
                to_son.add(r'!/user$')

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
                qnode_measure = measure.get_qnode_measure(submission.survey_id)
                parent = model.ResponseNode.from_qnode(
                    qnode_measure.qnode, submission)
                user = (session.query(model.AppUser)
                        .filter_by(id=response_history.user_id)
                        .first())
                dummy_relations = {
                    'parent': parent,
                    'measure': measure,
                    'submission': submission,
                    'user': user,
                }
                son.update(to_son(dummy_relations))

            # Always include the mtime of the most recent version. This is used
            # to avoid edit conflicts.
            dummy_relations = {
                'latest_modified': response.modified,
            }
            son.update(to_son(dummy_relations))

            def gather_variables(response):
                source_responses = {
                    mv.source_qnode_measure: model.Response.from_measure(
                        mv.source_qnode_measure, response.submission)
                    for mv in response.qnode_measure.source_vars}
                source_variables = {
                    source_qnode_measure: response and response.variables or {}
                    for source_qnode_measure, response in source_responses.items()}
                variables_by_target = {
                    mv.target_field:
                    source_variables[mv.source_qnode_measure].get(mv.source_field)
                    for mv in response.qnode_measure.source_vars}
                # Filter out blank/null variables
                return {k: v for k, v in variables_by_target.items() if v}
            son['sourceVars'] = gather_variables(response)

            # Explicit rollback to avoid committing dummy response.
            session.rollback()

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def get_version(self, session, response, version):
        if not version:
            return None

        try:
            version = int(version)
        except ValueError:
            raise errors.ModelError("Invalid version number")
        if version == response.version:
            return None

        history = (session.query(model.ResponseHistory)
            .get((response.submission_id, response.measure_id, version)))

        if history is None:
            raise errors.MissingDocError("No such version")
        return history

    def query(self, submission_id):
        '''Get a list.'''
        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == '':
            raise errors.ModelError("qnode ID required")

        with model.session_scope() as session:
            submission = (session.query(model.Submission)
                .filter_by(id=submission_id)
                .first())

            if submission is None:
                raise errors.MissingDocError("No such submission")
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
                r'^/[0-9]+/error$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/measure$',
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

        try:
            with model.session_scope(version=True) as session:
                submission = (session.query(model.Submission)
                    .get(submission_id))
                if submission is None:
                    raise errors.MissingDocError("No such submission")

                self._check_authz(submission)

                query = (session.query(model.Response).filter_by(
                     submission_id=submission_id, measure_id=measure_id))
                response = query.first()

                verbs = []
                if response is None:
                    program_id = submission.program_id
                    survey_id = submission.survey_id
                    qnode_measure = (session.query(model.QnodeMeasure)
                        .get((program_id, survey_id, measure_id)))
                    if qnode_measure is None:
                        raise errors.MissingDocError("No such measure")
                    response = model.Response(
                        qnode_measure=qnode_measure,
                        submission=submission,
                        approval='draft')
                    session.add(response)
                    verbs.append('create')
                else:
                    same_user = response.user.id == self.current_user.id
                    td = datetime.datetime.utcnow() - response.modified
                    hours_since_update = td.total_seconds() / 60 / 60

                    if same_user and hours_since_update < 8:
                        response.version_on_update = False

                    modified = self.request_son.get("latest_modified", 0)
                    # Convert to int to avoid string conversion errors during
                    # JSON marshalling.
                    if int(modified) < int(response.modified.timestamp()):
                        raise errors.ModelError(
                            "This response has changed since you loaded the"
                            " page. Please copy or remember your changes and"
                            " refresh the page.")
                    verbs.append('update')

                if self.request_son['approval'] != response.approval:
                    check_approval_change(
                        self.current_user.role, submission,
                        self.request_son['approval'])
                    verbs.append('state')

                self._update(response, self.request_son)
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
                    raise errors.ModelError(str(e))

                act = Activities(session)
                act.record(self.current_user, response, verbs)
                if not act.has_subscription(self.current_user, response):
                    act.subscribe(self.current_user, response.submission)
                    self.reason("Subscribed to submission")

        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(submission_id, measure_id)

    def _check_authz(self, submission):
        if not self.has_privillege('consultant'):
            if submission.organisation.id != self.organisation.id:
                raise errors.AuthzError(
                    "You can't modify another organisation's response")

    def _update(self, response, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(response, error_factory=errors.ModelError)
        update('comment', son, sanitise=True)
        update('not_relevant', son)
        update('response_parts', son)
        update('quality', son)

        extras = {
            'modified': datetime.datetime.utcnow(),
            'user_id': str(self.current_user.id),
        }

        update('approval', son)
        update('audit_reason', son)

        if object_session(response).is_modified(response):
            update('modified', extras)
            update('user_id', extras)

        # Attachments are stored elsewhere.


class ResponseHistoryHandler(base_handler.Paginate, base_handler.BaseHandler):
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
