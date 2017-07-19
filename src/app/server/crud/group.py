from tornado.escape import json_encode
import tornado.web

from activity import Activities
import base_handler
import errors
import model
from utils import ToSon, truthy, updater


class GroupHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, group_id):
        if not group_id:
            self.query()
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            group = session.query(model.Group).get(group_id)
            if not group:
                raise errors.MissingDocError("No such group")

            policy = user_session.policy.derive({
                'group': group,
            })
            policy.verify('group_view')

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

            son = to_son(group)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            query = session.query(model.Group)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Group.title.ilike(r'%{}%'.format(term)))

            policy = user_session.policy.derive({})
            policy.verify('group_browse')

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Group.deleted == deleted)

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
    def post(self, group_id):
        if group_id:
            raise errors.MethodError("Can't use POST for existing group.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            group = model.Group()
            self.update(group, self.request_son)
            self.update_auto(group)
            session.add(group)

            session.flush()

            policy = user_session.policy.derive({
                'group': group,
            })
            policy.verify('group_add')

            act = Activities(session)
            act.record(self.current_user, group, ['create'])
            if not act.has_subscription(self.current_user, group):
                act.subscribe(self.current_user, group)
                self.reason("Subscribed to group")

            group_id = str(group.id)

        self.get(group_id)

    @tornado.web.authenticated
    def put(self, group_id):
        if not group_id:
            raise errors.MethodError("Can't use PUT for new group.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            group = session.query(model.Group).get(group_id)
            if not group:
                raise errors.MissingDocError("No such group")

            self.update(group, self.request_son)

            verbs = []
            if session.is_modified(group):
                verbs.append('update')
                self.update_auto(group)

            if group.deleted:
                group.deleted = False
                verbs.append('undelete')

            policy = user_session.policy.derive({
                'group': group,
            })
            policy.verify('group_edit')

            session.flush()
            act = Activities(session)
            act.record(self.current_user, group, verbs)
            if not act.has_subscription(self.current_user, group):
                act.subscribe(self.current_user, group)
                self.reason("Subscribed to group")

            group_id = str(group.id)

        self.get(group_id)

    @tornado.web.authenticated
    def delete(self, group_id):
        if not group_id:
            raise errors.MethodError("Group ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            group = session.query(model.Group).get(group_id)
            if not group:
                raise errors.MissingDocError("No such group")

            policy = user_session.policy.derive({
                'group': group,
            })
            policy.verify('group_del')

            act = Activities(session)
            if not group.deleted:
                act.record(self.current_user, group, ['delete'])
            if not act.has_subscription(self.current_user, group):
                act.subscribe(self.current_user, group)
                self.reason("Subscribed to survey group")

            group.deleted = True

        self.get(group_id)

    def update(self, group, son):
        update = updater(group, error_factory=errors.ModelError)
        update('title', son)
        update('text', son)
        update('description', son, sanitise=True)
