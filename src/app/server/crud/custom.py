import datetime

from tornado.escape import json_encode
import tornado.web

from activity import Activities
import auth
import base_handler
import errors
import model
from utils import ToSon, truthy, updater


class CustomQueryHandler(base_handler.Paginate, base_handler.BaseHandler):
    @tornado.web.authenticated
    def get(self, query_id):
        if not query_id:
            self.query()
            return

        self._check_authz()

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            custom_query = session.query(model.CustomQuery).get(query_id)
            if custom_query is None:
                raise errors.MissingDocError("No such query")

            old_version = self.get_version(session, custom_query, version)

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

            if not old_version:
                son = to_son(custom_query)
            else:
                son = to_son(old_version)
                user = session.query(model.AppUser).get(old_version.user_id)
                if user:
                    son.user = to_son(user)

            # Always include the mtime of the most recent version. This is used
            # to avoid edit conflicts.
            dummy_relations = {
                'latest_modified': custom_query.modified,
            }
            son.update(to_son(dummy_relations))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def get_version(self, session, custom_query, version):
        if not version:
            return None

        try:
            version = int(version)
        except ValueError:
            raise errors.ModelError("Invalid version number")
        if version == custom_query.version:
            return None

        history = (
            session.query(model.CustomQueryHistory)
            .get((custom_query.id, version)))

        if history is None:
            raise errors.MissingDocError("No such version")
        return history

    def query(self):
        self._check_authz()

        with model.session_scope() as session:
            query = session.query(model.CustomQuery)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.CustomQuery.title.ilike(r'%{}%'.format(term)))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.CustomQuery.deleted == deleted)

            order_by = self.get_argument('order', 'title')
            if order_by == 'title':
                order_field = model.CustomQuery.title
            elif order_by == 'modified':
                order_field = model.CustomQuery.modified
            else:
                order_field = None

            if order_field:
                if self.get_argument('desc', ''):
                    order_field = order_field.desc()
                query = query.order_by(order_field)

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
    def post(self, query_id):
        self._check_authz()
        if query_id:
            raise errors.MethodError("Can't use POST for existing query.")

        with model.session_scope() as session:
            custom_query = model.CustomQuery()
            self.update(custom_query, self.request_son)
            self.update_auto(custom_query)
            session.add(custom_query)

            session.flush()
            act = Activities(session)
            act.record(self.current_user, custom_query, ['create'])
            if not act.has_subscription(self.current_user, custom_query):
                act.subscribe(self.current_user, custom_query)
                self.reason("Subscribed to query")

            query_id = str(custom_query.id)

        self.get(query_id)

    @tornado.web.authenticated
    def put(self, query_id):
        self._check_authz()
        if not query_id:
            raise errors.MethodError("Can't use PUT for new query.")

        with model.session_scope(version=True) as session:
            custom_query = session.query(model.CustomQuery).get(query_id)
            if custom_query is None:
                raise errors.MissingDocError("No such query")

            self.check_concurrent_write(custom_query)
            if not self.should_save_new_version(custom_query):
                custom_query.version_on_update = False

            self.update(custom_query, self.request_son)

            verbs = []
            if session.is_modified(custom_query):
                verbs.append('update')
                self.update_auto(custom_query)
            else:
                custom_query.version_on_update = False

            if custom_query.deleted:
                custom_query.deleted = False
                verbs.append('undelete')

            session.flush()
            act = Activities(session)
            act.record(self.current_user, custom_query, verbs)
            if not act.has_subscription(self.current_user, custom_query):
                act.subscribe(self.current_user, custom_query)
                self.reason("Subscribed to query")

            query_id = str(custom_query.id)

        self.get(query_id)

    def check_concurrent_write(self, custom_query):
        modified = self.request_son.get("latest_modified", 0)
        # Convert to int to avoid string conversion errors during
        # JSON marshalling.
        if int(modified) < int(custom_query.modified.timestamp()):
            raise errors.ModelError(
                "This query has changed since you loaded the"
                " page. Please copy or remember your changes and"
                " refresh the page.")

    def should_save_new_version(self, custom_query):
        same_user = custom_query.user.id == self.current_user.id
        td = datetime.datetime.utcnow() - custom_query.modified
        hours_since_update = td.total_seconds() / 60 / 60
        return not same_user or hours_since_update >= 8

    @auth.authz('admin')
    def delete(self, query_id):
        self._check_authz()
        if not query_id:
            raise errors.MethodError("Query ID required")

        with model.session_scope(version=False) as session:
            custom_query = session.query(model.CustomQuery).get(query_id)
            if custom_query is None:
                raise errors.MissingDocError("No such query")

            act = Activities(session)
            if not custom_query.deleted:
                act.record(self.current_user, custom_query, ['delete'])
            if not act.has_subscription(self.current_user, custom_query):
                act.subscribe(self.current_user, custom_query)
                self.reason("Subscribed to query")

            custom_query.deleted = True

        self.get(query_id)

    def update(self, custom_query, son):
        update = updater(custom_query, error_factory=errors.ModelError)
        update('title', son)
        update('text', son)
        update('description', son, sanitise=True)

    def update_auto(self, custom_query):
        extras = {
            'modified': datetime.datetime.utcnow(),
            'user_id': str(self.current_user.id),
        }
        update = updater(custom_query)
        update('modified', extras)
        update('user_id', extras)

    def _check_authz(self):
        if not self.has_privillege('admin'):
            raise errors.AuthzError("You can't use custom queries")


class CustomQueryHistoryHandler(
        base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, custom_query_id):
        '''Get a list of versions of a response.'''
        with model.session_scope() as session:
            # Current version
            versions = (
                session.query(model.CustomQuery)
                .filter_by(id=custom_query_id)
                .all())

            # Other versions
            query = (
                session.query(model.CustomQueryHistory)
                .filter_by(id=custom_query_id)
                .order_by(model.CustomQueryHistory.version.desc()))
            query = self.paginate(query)

            versions += query.all()

            # Important! If you're going to include the description field here,
            # make sure it is cleaned first to prevent XSS attacks.
            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/version$',
                r'/modified$',
                # Descend
                r'/[0-9]+$',
                r'/user$',
            )

            sons = to_son(versions)

            for son, version in zip(sons, versions):
                user = session.query(model.AppUser).get(version.user_id)
                if user is not None:
                    son['user'] = to_son(user)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
