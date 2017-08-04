import logging
import tempfile

import tornado
from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode
from concurrent.futures import ThreadPoolExecutor

import base_handler
import model
from utils import denormalise
from .importer import Importer


MAX_WORKERS = 4

log = logging.getLogger('app.importer.sub_import')


class ImportSubmissionHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        request_son = denormalise(json_decode(self.get_argument('submission')))
        program_id = request_son.program.id
        survey_id = request_son.survey.id
        organisation_id = request_son.organisation.id
        title = request_son.title

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            org = session.query(model.Organisation).get(organisation_id)
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

        program_id = yield self.background_task(
            user_id, program_id, survey_id, organisation_id, title)

        self.set_header("Content-Type", "text/plain")
        self.write(program_id)
        self.finish()

    @run_on_executor
    def background_task(
            self, user_id, program_id, survey_id, organisation_id, title):
        with tempfile.NamedTemporaryFile() as fd:
            fileinfo = self.request.files['file'][0]
            fd.write(fileinfo['body'])

            i = Importer()
            program_id = i.process_submission_file(
                fd.name, program_id, survey_id, organisation_id, title,
                user_id)

        return str(program_id)
