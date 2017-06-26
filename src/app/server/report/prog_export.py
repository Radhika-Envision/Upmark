from concurrent.futures import ThreadPoolExecutor
import os
import tempfile

from tornado import gen
import tornado.web
from tornado.concurrent import run_on_executor

import base_handler
import errors
from .export import Exporter
import model


BUF_SIZE = 4096
MAX_WORKERS = 4


class ExportProgramHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, program_id, survey_id, fmt, extension):
        if extension != 'xlsx':
            raise errors.MissingDocError(
                "File type not supported: %s" % extension)
        if fmt not in {'tabular', 'nested'}:
            raise errors.MissingDocError(
                "Unrecognised format: %s" % fmt)

        with model.session_scope() as session:
            self.check_browse_program(session, program_id, survey_id)

            survey = (session.query(model.Survey)
                         .get((survey_id, program_id)))
            if program_id != str(survey.program_id):
                raise errors.ModelError(
                    "Survey does not belong to specified program.")

        output_file = 'program_{0}_survey_{1}_{2}.xlsx'.format(
            program_id, survey_id, fmt)
        base_url = ("%s://%s" % (self.request.protocol,
                self.request.host))

        with tempfile.TemporaryDirectory() as tmpdirname:
            output_path = os.path.join(tmpdirname, output_file)
            if fmt == 'tabular':
                yield self.export_tabular(
                    output_path, program_id, survey_id,
                    self.current_user.role, base_url)
            else:
                yield self.export_nested(
                    output_path, program_id, survey_id,
                    self.current_user.role, base_url)
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment')

            with open(output_path, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    @run_on_executor
    def export_tabular(self, path, program_id, survey_id, user_role, base_url):
        e = Exporter()
        program_id = e.process_tabular(
            path, program_id, survey_id, None, user_role, base_url)

    @run_on_executor
    def export_nested(self, path, program_id, survey_id, user_role, base_url):
        e = Exporter()
        program_id = e.process_nested(
            path, program_id, survey_id, None, user_role, base_url)
