import logging
import tempfile

import tornado
from tornado import gen
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

import base_handler
import model
from .importer import Importer


MAX_WORKERS = 4

log = logging.getLogger('app.importer.prog_import')


class ImportStructureHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'user': user_session.user,
            })
            policy.verify('program_add')

        program_id = yield self.background_task()

        self.set_header("Content-Type", "text/plain")
        self.write(str(program_id))
        self.finish()

    @run_on_executor
    def background_task(self):
        with tempfile.NamedTemporaryFile() as fd:
            fileinfo = self.request.files['file'][0]
            fd.write(fileinfo['body'])

            importer = Importer()
            title = self.get_argument('title')
            description = self.get_argument('description')
            program_id = importer.process_structure_file(
                fd.name, title, description)

        return str(program_id)
