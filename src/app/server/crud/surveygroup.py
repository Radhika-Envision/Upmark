import cairosvg
from concurrent.futures import ThreadPoolExecutor
import os

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_encode
import tornado.web

from activity import Activities
import base_handler
import errors
import image
import model
from utils import ToSon, truthy, updater, get_package_dir, to_camel_case


MAX_WORKERS = 4
SCHEMA = {
    'group_logo': {
        'type': 'image',
        'accept': '.svg',
        'default_file_path': "../client/images/icon-sm.svg",
    }
}


class SurveyGroupIconHandler(base_handler.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, surveygroup_id):
        forceDefault = self.get_argument('default', None) != None

        with model.session_scope() as session:
            # Verify requested survey group exists
            surveygroup = session.query(model.SurveyGroup).get(surveygroup_id)
            if not surveygroup:
                raise errors.MissingDocError("No such survey group")

            # Verify user can view this survey group
            user_session = self.get_user_session(session)
            user_session.policy.verify('surveygroup_view')

            # Retrieve raw svg file
            icon = surveygroup.logo
            if not icon or forceDefault:
                path = os.path.join(
                    get_package_dir(), SCHEMA['group_logo']['default_file_path'])
                with open(path, 'rb') as f:
                    icon = f.read()

            self.set_header('Content-Type', 'image/svg+xml')

            size = self.get_argument('size', None)
            if size is not None:
                # Convert to png of specified size
                size = int(size)
                data = image.clean_svg(icon).encode('utf-8')
                icon = cairosvg.svg2png(
                    data, parent_width=size, parent_height=size)
                self.set_header('Content-Type', 'image/png')

        self.write(icon)
        self.finish()

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, surveygroup_id):
        with model.session_scope() as session:
            # Verify user can edit this survey group
            user_session = self.get_user_session(session)
            user_session.policy.verify('surveygroup_edit')

            fileinfo = self.request.files['file'][0]
            body = fileinfo['body']
            body = yield self.clean_svg(body)

            surveygroup = session.query(model.SurveyGroup).get(surveygroup_id)
            surveygroup.logo = body.encode('utf-8')

        self.finish()

    @tornado.web.authenticated
    def delete(self, surveygroup_id):
        with model.session_scope() as session:
            # Verify user can edit this survey group
            user_session = self.get_user_session(session)
            user_session.policy.verify('surveygroup_edit')

            # Set logo column to null
            sg = session.query(model.SurveyGroup).get(surveygroup_id)
            if sg and sg.logo:
                sg.logo = None;

        self.finish()

    @run_on_executor
    def clean_svg(self, svg):
        return image.clean_svg(svg)

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

            # Get group logo
            name = 'group_logo'
            s = SCHEMA.get(name).copy()
            s['name'] = to_camel_case(name)

            s['value'] = surveygroup.logo
            if s['value'] is None:
                path = os.path.join(get_package_dir(), s['default_file_path'])
                with open(path, 'rb') as f:
                    s['value'] = f.read()

            del s['default_file_path']
            son[to_camel_case(name)] = ToSon()(s)

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
