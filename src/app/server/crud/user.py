import passwordmeter
from tornado.escape import json_encode
import tornado.web
from sqlalchemy.orm import joinedload
import voluptuous
from voluptuous import Extra, All, Required, Schema

from activity import Activities
import base_handler
import config
import errors
import model
from surveygroup_actions import assign_surveygroups, filter_surveygroups
from utils import ToSon, truthy, updater


def test_password(text):
    with model.session_scope() as session:
        setting = config.get_setting(session, 'pass_threshold')
        threshold = float(setting)
    password_tester = passwordmeter.Meter(settings={
        'threshold': threshold,
        'pessimism': 10,
        'factor.casemix.weight': 0.3})
    strength, improvements = password_tester.test(text)
    return strength, threshold, improvements


user_input_schema = Schema({
    Required('organisation'): All({
        Required('id'): str,
        Extra: object,
    }, msg="Organisation is invalid"),
    Extra: object,
})


class UserHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, user_id):
        '''
        Get a single user.
        '''
        if not user_id:
            self.query()
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            if user_id == 'current':
                user = user_session.user
            else:
                user = (
                    session.query(model.AppUser)
                    .options(joinedload('organisation'))
                    .options(joinedload('surveygroups'))
                    .get(user_id))
                if not user:
                    raise errors.MissingDocError("No such user")

            policy = user_session.policy.derive({
                'user': user,
                'surveygroups': user.surveygroups,
            })
            policy.verify('user_view')

            # Check that user shares a common surveygroup with the requesting
            # user.
            # Allow admins to access users outside their surveygroups though.
            if not policy.check('admin'):
                policy.verify('surveygroup_interact')

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/title$',
                r'/email$',
                r'/email_interval$',
                r'/role$',
                r'/deleted$',
                # Descend into nested objects
                r'/organisation$',
                r'/[0-9+]$',
                # Exclude password from response. Not really necessary because
                # 1. it's hashed and 2. it's not in the list above. But just to
                # be safe.
                r'!password',
            )
            if policy.check('surveygroup_browse'):
                to_son.add(r'^/surveygroups$')
            son = to_son(user)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''
        Get a list of users.
        '''

        sons = []
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            organisation_id = self.get_argument("organisationId", None)
            if organisation_id:
                org = session.query(model.Organisation).get(organisation_id)
            else:
                org = None

            policy = user_session.policy.derive({
                'org': org,
            })
            policy.verify('user_browse')

            query = (
                session.query(model.AppUser)
                .join(model.Organisation))

            # Filter out users that don't share a surveygroup with the
            # requesting user.
            # Allow admins to access users outside their surveygroups though.
            if not policy.check('admin'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [], [model.user_surveygroup])

            # Get all users for an organisation
            if organisation_id:
                query = query.filter(model.Organisation.id == organisation_id)

            # Get all users for a survey group
            surveygroup_id = self.get_argument("surveyGroupId", None)
            if surveygroup_id:
                query = (
                    query.join(model.SurveyGroup, model.AppUser.surveygroups)
                    .filter(model.SurveyGroup.id == surveygroup_id))

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.AppUser.name.ilike(r'%{}%'.format(term)))

            deleted = self.get_argument('deleted', None)
            if deleted is not None:
                deleted = truthy(deleted)

            # Filter deleted users. If organisation_id is not specified, users
            # inherit their organisation's deleted flag too.
            if deleted == True and not organisation_id:
                query = query.filter(
                    (model.AppUser.deleted == True) |
                    (model.Organisation.deleted == True))
            elif deleted == False and not organisation_id:
                query = query.filter(
                    (model.AppUser.deleted == False) &
                    (model.Organisation.deleted == False))
            elif deleted == True:
                query = query.filter(model.AppUser.deleted == True)
            elif deleted == False:
                query = query.filter(model.AppUser.deleted == False)

            query = query.order_by(model.AppUser.name)
            query = self.paginate(query)

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/deleted$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/organisation$',
                # Exclude password from response. Not really necessary because
                # 1. it's hashed and 2. it's not in the list above. But just to
                # be safe.
                r'!password'
            )

            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, user_id):
        '''
        Create a new user.
        '''
        if user_id:
            raise errors.MethodError("Can't use POST for existing users.")

        try:
            user_input_schema(self.request_son)
        except voluptuous.error.Invalid as e:
            raise errors.ModelError.from_voluptuous(e)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = (
                session.query(model.Organisation)
                .get(self.request_son['organisation']['id']))
            if not org:
                raise errors.ModelError("No such organisation")

            user = model.AppUser(organisation=org)

            try:
                assign_surveygroups(user_session, user, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            policy = user_session.policy.derive({
                'org': user.organisation,
                'user': user,
                'target': self.request_son,
                'surveygroups': user.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('user_add')
            policy.verify('user_change_role')
            self.check_password(self.request_son.password)

            self._update(user, self.request_son, session)
            session.add(user)

            # Need to flush so object has an ID to record action against.
            session.flush()

            act = Activities(session)
            act.record(user_session.user, user, ['create'])
            act.ensure_subscription(
                user_session.user, user, user.organisation, self.reason)
            act.subscribe(user, user.organisation)
            self.reason("New user subscribed to organisation")

            user_id = user.id
        self.get(user_id)

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Update an existing user.
        '''
        if not user_id:
            raise errors.MethodError("Can't use PUT for new users (no ID).")

        try:
            user_input_schema(self.request_son)
        except voluptuous.error.Invalid as e:
            raise errors.ModelError.from_voluptuous(e)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise errors.MissingDocError("No such user")

            try:
                groups_changed = assign_surveygroups(
                    user_session, user, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            policy = user_session.policy.derive({
                'org': user.organisation,
                'user': user,
                'target': self.request_son,
                'surveygroups': user.surveygroups,
            })
            policy.verify('user_edit')

            # Check that user shares a common surveygroup with the requesting
            # user.
            # Allow admins to edit users outside their surveygroups though.
            if not policy.check('admin'):
                policy.verify('surveygroup_interact')

            if self.request_son.role and self.request_son.role != user.role:
                policy.verify('user_change_role')

            if ('deleted' in self.request_son and
                    self.request_son['deleted'] != user.deleted):
                policy.verify('user_enable')

            if self.request_son.get('password'):
                self.check_password(self.request_son.password)

            verbs = []
            oid = self.request_son.organisation.id
            if oid != str(user.organisation_id):
                policy.verify('user_change_org')
                verbs.append('relation')

            self._update(user, self.request_son, session)

            act = Activities(session)
            if session.is_modified(user) or groups_changed:
                verbs.append('update')

            if user.deleted:
                user.deleted = False
                verbs.append('undelete')

            session.flush()
            if len(verbs) > 0:
                act.record(user_session.user, user, verbs)
                act.ensure_subscription(
                    user_session.user, user, user.organisation, self.reason)
                if not act.has_subscription(user, user):
                    act.subscribe(user, user.organisation)
                    self.reason("User subscribed to organisation")

        self.get(user_id)

    @tornado.web.authenticated
    def delete(self, user_id):
        if not user_id:
            raise errors.MethodError("User ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise errors.MissingDocError("No such user")

            policy = user_session.policy.derive({
                'org': user.organisation,
                'user': user,
                'surveygroups': user.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('user_del')

            act = Activities(session)
            if not user.deleted:
                act.record(user_session.user, user, ['delete'])
            act.ensure_subscription(
                user_session.user, user, user.organisation, self.reason)

            user.deleted = True

        self.finish()

    def check_password(self, password):
        if password:
            strength, threshold, _ = test_password(password)
            if strength < threshold:
                raise errors.ModelError("Password is not strong enough")

    def _update(self, user, son, session):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(user, error_factory=errors.ModelError)
        update('email', son)
        update('email_interval', son)
        update('name', son)
        update('role', son)
        update('password', son)

        org = (
            session.query(model.Organisation)
            .get(son.organisation.id))
        if not org:
            raise errors.ModelError("No such organisation")
        user.organisation = org


class PasswordHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def post(self):
        '''
        Check the strength of a password.
        '''

        if 'password' not in self.request_son:
            raise errors.ModelError("Please specify a password")

        strength, threshold, improvements = test_password(
            self.request_son['password'])
        son = {
            'threshold': threshold,
            'strength': strength,
            'improvements': improvements
        }

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()
