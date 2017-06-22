import datetime

from tornado.escape import json_encode
import tornado.web

from activity import Activities
import auth
import base_handler
import errors
import model
from utils import ToSon, truthy, updater


class ProjectHandler(base_handler.Paginate, base_handler.BaseHandler):
    @tornado.web.authenticated
    def get(self, project_id):
        if not project_id:
            self.query()
            return

        self._check_authz()

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            project = session.query(model.Project).get(project_id)
            if project is None:
                raise errors.MissingDocError("No such project")

            old_version = self.get_version(session, project, version)

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

            son = to_son(project)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        self._check_authz()

        with model.session_scope() as session:
            query = session.query(model.Project)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Project.title.ilike(r'%{}%'.format(term)))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Project.deleted == deleted)

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
    def post(self, project_id):
        self._check_authz()
        if project_id:
            raise errors.MethodError("Can't use POST for existing project.")

        with model.session_scope() as session:
            project = model.Project()
            self.update(project, self.request_son)
            self.update_auto(project)
            session.add(project)

            session.flush()
            act = Activities(session)
            act.record(self.current_user, project, ['create'])
            if not act.has_subscription(self.current_user, project):
                act.subscribe(self.current_user, project)
                self.reason("Subscribed to project")

            project_id = str(project.id)

        self.get(project_id)

    @tornado.web.authenticated
    def put(self, project_id):
        self._check_authz()
        if not project_id:
            raise errors.MethodError("Can't use PUT for new project.")

        with model.session_scope(version=True) as session:
            project = session.query(model.Project).get(project_id)
            if project is None:
                raise errors.MissingDocError("No such project")

            self.update(project, self.request_son)

            verbs = []
            if session.is_modified(project):
                verbs.append('update')
                self.update_auto(project)

            if project.deleted:
                project.deleted = False
                verbs.append('undelete')

            session.flush()
            act = Activities(session)
            act.record(self.current_user, project, verbs)
            if not act.has_subscription(self.current_user, project):
                act.subscribe(self.current_user, project)
                self.reason("Subscribed to project")

            project_id = str(project.id)

        self.get(project_id)

    @auth.authz('admin')
    def delete(self, project_id):
        self._check_authz()
        if not project_id:
            raise errors.MethodError("Project ID required")

        with model.session_scope(version=False) as session:
            project = session.query(model.Project).get(project_id)
            if project is None:
                raise errors.MissingDocError("No such project")

            act = Activities(session)
            if not project.deleted:
                act.record(self.current_user, project, ['delete'])
            if not act.has_subscription(self.current_user, project):
                act.subscribe(self.current_user, project)
                self.reason("Subscribed to project")

            project.deleted = True

        self.get(project_id)

    def update(self, project, son):
        update = updater(project, error_factory=errors.ModelError)
        update('title', son)
        update('text', son)
        update('description', son, sanitise=True)

    def update_auto(self, project):
        extras = {
            'modified': datetime.datetime.utcnow(),
            'user_id': str(self.current_user.id),
        }
        update = updater(project)
        update('modified', extras)
        update('user_id', extras)

    def _check_authz(self):
        if not self.has_privillege('admin'):
            raise errors.AuthzError("You can't use custom queries")
