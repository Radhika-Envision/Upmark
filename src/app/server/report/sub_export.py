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


class ExportSubmissionHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, submission_id, fmt, extension):
        if extension != 'xlsx':
            raise errors.MissingDocError(
                "File type not supported: %s" % extension)
        if fmt not in {'tabular', 'nested'}:
            raise errors.MissingDocError(
                "Unrecognised format: %s" % fmt)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            submission = (session.query(model.Submission)
                          .get(submission_id))
            if not submission:
                raise errors.MissingDocError("No such submission")
            elif submission.deleted:
                raise errors.MissingDocError(
                    "That submission has been deleted")

            policy = user_session.policy.derive({
                'org': submission.organisation,
                'survey': submission.survey,
            })
            policy.verify('report_sub_export')

        output_file = 'submission_{0}_{1}.xlsx'.format(submission_id, fmt)
        base_url = ("%s://%s" % (
            self.request.protocol, self.request.host))

        with tempfile.TemporaryDirectory() as tmpdirname:
            output_path = os.path.join(tmpdirname, output_file)
            if fmt == 'tabular':
                yield self.export_tabular(
                    output_path, program_id, survey_id, submission_id,
                    self.current_user.role, base_url)
            else:
                yield self.export_nested(
                    output_path, program_id, survey_id, submission_id,
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
    def export_tabular(self, path, program_id, survey_id,
                       submission_id, user_role, base_url):
        e = Exporter()
        program_id = e.process_tabular(
            path, program_id, survey_id, submission_id,
            user_role, base_url)

    @run_on_executor
    def export_nested(self, path, program_id, survey_id,
                      submission_id, user_role, base_url):
        e = Exporter()
        program_id = e.process_nested(
            path, program_id, survey_id, submission_id,
            user_role, base_url)
