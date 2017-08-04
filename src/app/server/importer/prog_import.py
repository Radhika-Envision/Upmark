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

log = logging.getLogger('app.importer.prog_import')


class ImportStructureHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        request_son = denormalise(json_decode(self.get_argument('program')))
        surveygroup_ids = [sg.id for sg in request_son.surveygroups]

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            surveygroups = (
                session.query(model.SurveyGroup)
                .filter(model.SurveyGroup.id.in_(surveygroup_ids))
                .all())

            policy = user_session.policy.derive({
                'user': user_session.user,
                'surveygroups': surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_add')

        program_id = yield self.background_task(
            request_son.title, request_son.description, surveygroup_ids)

        self.set_header("Content-Type", "text/plain")
        self.write(str(program_id))
        self.finish()

    @run_on_executor
    def background_task(self, title, description, surveygroup_ids):
        with tempfile.NamedTemporaryFile() as fd:
            fileinfo = self.request.files['file'][0]
            fd.write(fileinfo['body'])

            importer = Importer()
            program_id = importer.process_structure_file(
                fd.name, title, description, surveygroup_ids)

        return str(program_id)
