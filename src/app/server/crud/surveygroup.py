from tornado.escape import json_encode
import tornado.web

from activity import Activities
import base_handler
import errors
import model
from utils import ToSon, truthy, updater


class SurveyGroupHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, surveygroup_id):
        if not surveygroup_id:
            self.query()
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            surveygroup = session.query(model.SurveyGroup).get(surveygroup_id)
            if not surveygroup:
                raise errors.MissingDocError("No such survey group")

            policy = user_session.policy.derive({
                'surveygroups': {surveygroup},
            })
            policy.verify('surveygroup_view')

            to_son = ToSon(
                r'/id$',
                r'/deleted$',
                r'/modified$',
                r'/latest_modified$',
                r'/user$',
                r'/title$',
                r'/description$',
                r'/name$',
                r'/text$',
                r'/version$',
            )

            son = to_son(surveygroup)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            query = session.query(model.SurveyGroup)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.SurveyGroup.title.ilike(r'%{}%'.format(term)))

            policy = user_session.policy.derive({})
            policy.verify('surveygroup_browse')

            if not policy.check('surveygroup_browse_all'):
                query = (
                    query
                    .join(model.user_surveygroup)
                    .filter(
                        model.user_surveygroup.columns.user_id ==
                        user_session.user.id))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.SurveyGroup.deleted == deleted)

            query = self.paginate(query)

            to_son = ToSon(
                r'^/[0-9]+/id$',
                r'/deleted$',
                r'/title$',
                r'/description$',
                r'/modified$',
                # Descend into list
                r'/[0-9]+$',
            )
            sons = to_son(query.all())
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, surveygroup_id):
        if surveygroup_id:
            raise errors.MethodError(
                "Can't use POST for existing survey group.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            surveygroup = model.SurveyGroup()
            self.update(surveygroup, self.request_son)
            session.add(surveygroup)

            session.flush()

            policy = user_session.policy.derive({
                'surveygroups': {surveygroup},
            })
            policy.verify('surveygroup_add')

            act = Activities(session)
            act.record(user_session.user, surveygroup, ['create'])
            act.ensure_subscription(
                user_session.user, surveygroup, surveygroup, self.reason)

            surveygroup_id = str(surveygroup.id)

        self.get(surveygroup_id)

    @tornado.web.authenticated
    def put(self, surveygroup_id):
        if not surveygroup_id:
            raise errors.MethodError("Can't use PUT for new group.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            surveygroup = session.query(model.SurveyGroup).get(surveygroup_id)
            if not surveygroup:
                raise errors.MissingDocError("No such survey group")

            self.update(surveygroup, self.request_son)

            verbs = []
            if session.is_modified(surveygroup):
                verbs.append('update')

            if surveygroup.deleted:
                surveygroup.deleted = False
                verbs.append('undelete')

            policy = user_session.policy.derive({
                'surveygroups': {surveygroup},
            })
            policy.verify('surveygroup_edit')

            session.flush()
            act = Activities(session)
            act.record(user_session.user, surveygroup, verbs)
            act.ensure_subscription(
                user_session.user, surveygroup, surveygroup, self.reason)

            surveygroup_id = str(surveygroup.id)

        self.get(surveygroup_id)

    @tornado.web.authenticated
    def delete(self, surveygroup_id):
        if not surveygroup_id:
            raise errors.MethodError("SurveyGroup ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            surveygroup = session.query(model.SurveyGroup).get(surveygroup_id)
            if not surveygroup:
                raise errors.MissingDocError("No such survey group")

            policy = user_session.policy.derive({
                'surveygroups': {surveygroup},
            })
            policy.verify('surveygroup_del')

            act = Activities(session)
            if not surveygroup.deleted:
                act.record(user_session.user, surveygroup, ['delete'])
            act.ensure_subscription(
                user_session.user, surveygroup, surveygroup, self.reason)

            surveygroup.deleted = True

        self.get(surveygroup_id)

    def update(self, surveygroup, son):
        update = updater(surveygroup, error_factory=errors.ModelError)
        update('title', son)
        update('description', son, sanitise=True)
