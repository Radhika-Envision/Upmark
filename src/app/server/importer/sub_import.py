import logging
import tempfile

import tornado
from tornado import gen
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

import base_handler
import errors
import model
from .importer import Importer


MAX_WORKERS = 4

log = logging.getLogger('app.importer.sub_import')


class ImportSubmissionHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        org_id = self.get_argument('organisation')
        if not org_id:
            raise errors.ModelError("Missing organisation ID")

        program_id = self.get_argument('program')
        if not program_id:
            raise errors.ModelError("Missing program ID")

        survey_id = self.get_argument('survey')
        if not survey_id:
            raise errors.ModelError("Missing survey ID")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            org = session.query(model.Organisation).get(org_id)
            survey = (
                session.query(model.Survey)
                .get((survey_id, program_id)))

            policy = user_session.policy.derive({
                'user': user_session.user,
                'org': org,
                'survey': survey,
            })
            policy.verify('submission_add')

            user_id = user_session.user.id

        program_id = yield self.background_task(user_id)

        self.set_header("Content-Type", "text/plain")
        self.write(program_id)
        self.finish()

    @run_on_executor
    def background_task(self, user_id):
        with tempfile.NamedTemporaryFile() as fd:
            fileinfo = self.request.files['file'][0]
            fd.write(fileinfo['body'])

            i = Importer()
            program_id = self.get_argument('program')
            organisation_id = self.get_argument('organisation')
            survey_id = self.get_argument("survey")
            title = self.get_argument('title')
            program_id = i.process_submission_file(
                fd.name, program_id, survey_id, organisation_id, title,
                user_id)

        return str(program_id)
