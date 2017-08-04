import datetime
import logging
import re
import sqlalchemy
import tempfile
import xlrd

import tornado
from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode
from concurrent.futures import ThreadPoolExecutor

import errors
import base_handler
import model
from score import Calculator
from utils import denormalise
from .utils import col2num
from .errors import ImportError


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

        submission_id = yield self.background_task(
            program_id, survey_id, organisation_id, title)

        self.set_header("Content-Type", "text/plain")
        self.write(str(submission_id))
        self.finish()

    @run_on_executor
    def background_task(
            self, program_id, survey_id, organisation_id, title):

        with tempfile.NamedTemporaryFile() as fd:
            fileinfo = self.request.files['file'][0]
            fd.write(fileinfo['body'])
            all_rows = self.read_sheet(fd.name)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            org = session.query(model.Organisation).get(organisation_id)
            if not org:
                raise errors.ModelError("No such organisation")

            survey = (
                session.query(model.Survey)
                .get((survey_id, program_id)))
            if not survey:
                raise errors.ModelError("No such survey")

            submission = model.Submission()
            submission.program = survey.program
            submission.survey = survey
            submission.organisation = org
            submission.title = title
            submission.approval = 'draft'
            session.add(submission)
            session.flush()
            submission_id = submission.id

            policy = user_session.policy.derive({
                'org': org,
                'survey': survey,
                'surveygroups': submission.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('submission_add')

            self.process_submission_file(
                all_rows, session, submission, user_session.user)

        return submission_id

    def read_sheet(self, path):
        with xlrd.open_workbook(path) as book:
            sheet = book.sheet_by_index(0)
            all_rows = [
                sheet.row_values(row_i)
                for row_i in range(1, sheet.nrows - 1)]
        return all_rows

    def process_submission_file(self, all_rows, session, submission, user):
        program_qnodes = (
            session.query(model.QuestionNode)
            .filter_by(program_id=submission.program.id))

        try:
            order = title = ''
            for row_num in range(0, len(all_rows) - 1):
                order, title = self.parse_order_title(all_rows, row_num, "A")
                function = program_qnodes.filter_by(
                    parent_id=None, title=title).one()
                log.debug("function: %s", function)
                function_order = order

                order, title = self.parse_order_title(all_rows, row_num, "B")
                process = program_qnodes.filter_by(
                    parent_id=function.id, title=title).one()
                log.debug("process: %s", process)

                order, title = self.parse_order_title(all_rows, row_num, "C")
                subprocess = program_qnodes.filter_by(
                    parent_id=process.id, title=title).one()
                log.debug("subprocess: %s", subprocess)

                order, title = self.parse_order_title(all_rows, row_num, "D")
                measure = [
                    qm.measure for qm in subprocess.qnode_measures
                    if qm.measure.title.split('\n')[0] == title]

                if len(measure) == 1:
                    measure = measure[0]
                else:
                    raise Exception(
                        "This survey does not match the target survey.")
                log.debug("measure: %s", measure)

                log.debug(
                    "measure response_type: %s",
                    measure.response_type.name)

                response = model.Response()
                response.program_id = submission.program.id
                response.survey_id = submission.survey.id
                response.measure_id = measure.id
                response.submission_id = submission.id
                response.user_id = user.id
                response.comment = all_rows[row_num][col2num("K")]
                # FIXME: Hard-coded; should be read from file
                response.not_relevant = False
                response.modified = datetime.datetime.utcnow()
                response.approval = 'draft'
                response_part = []

                response_part.append(self.parse_response_type(
                    all_rows, row_num, measure.response_type, "E"))
                if function_order != "7":
                    response_part.append(self.parse_response_type(
                        all_rows, row_num, measure.response_type, "F"))
                    response_part.append(self.parse_response_type(
                        all_rows, row_num, measure.response_type, "G"))
                    response_part.append(self.parse_response_type(
                        all_rows, row_num, measure.response_type, "H"))
                response.response_parts = response_part
                response.audit_reason = "Import"
                session.add(response)
        except sqlalchemy.orm.exc.NoResultFound:
            raise errors.ModelError(
                "Survey structure does not match: Row %d: %s %s" %
                (row_num + 2, order, title))
        except ImportError as e:
            raise errors.ModelError(
                "Row %d: %s %s: %s" %
                (row_num + 2, order, title, str(e)))
        except Exception as e:
            raise errors.InternalModelError(
                "Row %d: %s %s: %s" %
                (row_num + 2, order, title, str(e)))

        calculator = Calculator.scoring(submission)
        calculator.mark_entire_survey_dirty(submission.survey)
        calculator.execute()

    def parse_response_type(self, all_rows, row_num, response_type, col_chr):
        response_text = all_rows[row_num][col2num(col_chr)]
        index = ord(col_chr) - ord("E")

        try:
            response_options = [
                r["name"].replace(" ", "").lower()
                for r in response_type.parts[index]["options"]]
        except IndexError:
            raise ImportError(
                "This measure only has %d part(s)" %
                len(response_type.parts))

        try:
            response_index = response_options.index(
                response_text.replace(" ", "").lower())
        except (AttributeError, ValueError) as e:
            raise ImportError(
                "Response %d: '%s' is not a valid option" %
                (index + 1, response_text))

        return {"index": response_index, "note": response_text}

    CHOICE_PATTERN = re.compile(r'(?P<order>[\d.]+) (?P<title>.+)')

    def parse_order_title(self, all_rows, row_num, col_chr):
        col_num = col2num(col_chr)
        cell = all_rows[row_num][col_num]
        match = self.CHOICE_PATTERN.match(cell)
        if not match:
            raise ImportError("Could not parse cell %s%s" % (row_num, col_chr))
        order = match.group('order')
        title = match.group('title').replace("\n", chr(10))
        return order, title
