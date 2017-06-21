import datetime
import json
import logging
import os
import re
import sqlalchemy
import string
import tempfile
import threading
import xlrd

import bleach
from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

import app
import auth
import errors
import handlers
import model
import response_type
from score import Calculator


MAX_WORKERS = 4

log = logging.getLogger('app.import_handler')


class ImportError(Exception):
    pass


class ImportStructureHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @auth.authz('author')
    @gen.coroutine
    def post(self):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        try:
            fd.write(fileinfo['body'])
            program_id = yield self.background_task(fd.name)
        finally:
            fd.close()
        self.set_header("Content-Type", "text/plain")
        self.write(program_id)
        self.finish()

    @run_on_executor
    def background_task(self, file_path):
        i = Importer()
        title = self.get_argument('title')
        description = self.get_argument('description')
        program_id = i.process_structure_file(file_path, title, description)
        return program_id


class ImportResponseHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @auth.authz('author')
    @gen.coroutine
    def post(self, program_id):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        try:
            fd.write(fileinfo['body'])
            yield self.background_task(fd.name)
        finally:
            fd.close()
        self.set_header("Content-Type", "text/plain")
        self.write("Task finished")
        self.finish()

    @run_on_executor
    def background_task(self, file_path):
        i = Importer()
        title = self.request.title
        description = self.request.description
        i.process_structure_file(file_path, title, description)


class ImportSubmissionHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @auth.authz('author')
    @gen.coroutine
    def post(self):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        try:
            fd.write(fileinfo['body'])
            program_id = yield self.background_task(fd.name)
        finally:
            fd.close()

        self.set_header("Content-Type", "text/plain")
        self.write(program_id)
        self.finish()

    @run_on_executor
    def background_task(self, file_path):
        i = Importer()
        program_id = self.get_argument('program')
        organisation_id = self.get_argument('organisation')
        survey_id = self.get_argument("survey")
        title = self.get_argument('title')
        user_id = self.get_current_user().id
        program_id = i.process_submission_file(file_path, program_id, survey_id, organisation_id, title, user_id)
        return program_id


class Importer():

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_structure_file(self, path, title, description):
        """
        Open and read an Excel file
        """
        all_rows = []
        with xlrd.open_workbook(path) as book:
            scoring_sheet = book.sheet_by_name("Scoring")

            for row_num in range(0, scoring_sheet.nrows - 1):
                row = scoring_sheet.row_values(row_num)
                all_rows.append(row)

        model.connect_db(os.environ.get('DATABASE_URL'))

        with model.session_scope() as session:

            program = model.Program()
            program.title = title
            program.description = bleach.clean(description, strip=True)
            session.add(program)
            response_types = {}
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                'aquamark_response_types.json')) as file:
                program.response_types = json.load(file)
                for rt_def in response_types:
                    response_type = model.ResponseType(
                        program=program,
                        name=rt_def['name'],
                        parts=rt_def['parts'],
                        formula=rt_def.get('formula'))
                    session.add(response_type)
                    response_types[rt_def['id']] = response_type
            program_id = str(program.id)

            survey = model.Survey()
            survey.program_id = program.id
            survey.title = "Imported Survey"
            survey.description = None
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                'aquamark_hierarchy.json')) as data_file:
                survey.structure = json.load(data_file)
            session.add(survey)
            session.flush()

            log.info("survey: %s" % survey.id)

            function_title_row = [{
                "title": row[self.col2num("J")],
                "order": row[self.col2num("C")],
                "row_num": all_rows.index(row)
            } for row in all_rows
                if str(row[self.col2num("S")]) == "Function Header"]

            process_title_row = [{
                "title": row[self.col2num("J")],
                "order": row[self.col2num("D")],
                "row_num": all_rows.index(row)
            } for row in all_rows
                if str(row[self.col2num("S")]) == "Process Header"]

            subprocess_title_row = [{
                "title": row[self.col2num("J")],
                "order": row[self.col2num("E")],
                "row_num": all_rows.index(row)
            } for row in all_rows
                if str(row[self.col2num("S")]) == "SubProcess Header"]

            for function in function_title_row:
                function_order = int(function['order'])
                function_title = function['title'].replace("{} - ".format(
                    function_order), "")
                function_description = self.parse_description(
                    all_rows, function['row_num'])

                qnode_function = model.QuestionNode()
                qnode_function.program_id = program.id
                qnode_function.survey_id = survey.id
                qnode_function.seq = function_order - 1
                qnode_function.title = function_title
                qnode_function.description = bleach.clean(
                    function_description, strip=True)

                session.add(qnode_function)
                session.flush()

                process_row = [row for row in process_title_row if "{}.".format(function_order) in row['title']]

                for process in process_row:
                    process_order = int(process['order'])
                    process_title = process['title'].replace("{}.{} - ".format(
                                                            function_order, process_order), "")

                    # print("process order:", process_order)
                    # print("process title:", process_title)
                    process_description = self.parse_description(
                        all_rows, process['row_num'], "")

                    qnode_process = model.QuestionNode()
                    qnode_process.program_id = program.id
                    qnode_process.survey_id = survey.id
                    qnode_process.parent_id = qnode_function.id
                    qnode_process.seq = process_order - 1
                    qnode_process.title = process_title
                    qnode_process.description = bleach.clean(
                        process_description, strip=True)
                    # log.info("qnode_process: %s" % qnode_process)
                    session.add(qnode_process)
                    session.flush()

                    subprocess_row = [row for row in subprocess_title_row if "{}.{}.".format(
                        function_order, process_order) in row['title']]
                    for subprocess in subprocess_row:
                        subprocess_order = int(subprocess['order'])
                        subprocess_title = subprocess['title'].replace("{}.{}.{} - ".format(
                                                                        function_order, process_order, subprocess_order), "")

                        # print("subprocess order:", subprocess_order)
                        # print("subprocess title:", subprocess_title)
                        subprocess_description = self.parse_description(
                            all_rows, subprocess['row_num'], "")

                        qnode_subprocess = model.QuestionNode()
                        qnode_subprocess.program_id = program.id
                        qnode_subprocess.survey_id = survey.id
                        qnode_subprocess.parent_id = qnode_process.id
                        qnode_subprocess.seq = subprocess_order - 1
                        qnode_subprocess.title = subprocess_title
                        qnode_subprocess.description = bleach.clean(
                            subprocess_description, strip=True)

                        session.add(qnode_subprocess)
                        session.flush()

                        measure_title_row = [{"title": row[self.col2num("k")], "row_num": all_rows.index(row), "order": row[self.col2num("F")], "weight": row[self.col2num("L")], "resp_num": row[self.col2num("F")]}
                                             for row in all_rows
                                             if function_order == row[self.col2num("C")] and
                                             process_order == row[self.col2num("D")] and
                                             subprocess_order == row[self.col2num("E")] and
                                             row[self.col2num("F")] != 0 and
                                             row[self.col2num("G")] == 1]

                        for measure in measure_title_row:
                            measure_order = int(measure["order"])
                            measure_title = measure['title'].replace("{}.{}.{}.{} - ".format(
                                            function_order, process_order, subprocess_order, measure_order), "")

                            measure_description = self.parse_description(
                                all_rows, measure['row_num'], "Description")
                            # Comments are part of the response, so ignore that row
                            measure_weight = measure['weight']

                            m = model.Measure()
                            m.program_id = program.id
                            m.title = measure_title
                            m.weight = measure_weight
                            m.description = bleach.clean(measure_description, strip=True)
                            rt_id = "standard"
                            if function_order == 7:
                                rt_id = "business-support-%s" % int(measure['resp_num'])
                            # log.info("response_type: %s", rt_id)
                            m.response_type = response_types[rt_id]
                            session.add(m)
                            session.flush()
                            qnode_measure = QnodeMeasure(
                                program=program, survey=survey,
                                parent=qnode_subprocess, measure=m)
                            qnode_subprocess.qnode_measures.reorder()
                            session.flush()

            calculator = Calculator.structural()
            calculator.mark_entire_survey_dirty(survey)
            calculator.execute()

            return program_id

    def process_response_file(self, path, program_id):
        """
        Open and read an Excel file
        """
        book = xlrd.open_workbook(path)
        scoring_sheet = book.sheet_by_name("Scoring")
        '''
        TODO : process response
        '''

    def process_submission_file(self, path, program_id, survey_id, organisation_id, title, user_id):
        """
        Open and read an Excel file
        """
        all_rows = []
        with xlrd.open_workbook(path) as book:
            sheet = book.sheet_by_index(0)

            # read rows
            for row_num in range(0, sheet.nrows - 1):
                row = sheet.row_values(row_num)
                all_rows.append(row)

        model.connect_db(os.environ.get('DATABASE_URL'))

        with model.session_scope() as session:
            program = session.query(model.Program).get(program_id)
            if program is None:
                raise Exception("There is no program.")

            survey = (session.query(model.Survey)
                .filter_by(id=survey_id, program_id=program.id)
                .one())
            if survey is None:
                raise Exception("There is no survey.")

            submission = model.Submission()
            submission.program_id = program.id
            submission.survey_id = survey.id
            submission.organisation_id = organisation_id
            submission.title = title
            submission.approval = 'draft'
            session.add(submission)
            session.flush()

            all_rows = []
            for row_num in range(1, sheet.nrows - 1):
                cell = sheet.row_values(row_num)
                all_rows.append(cell)

            function_col_num = self.col2num("A")
            process_col_num = self.col2num("B")
            subprocess_col_num = self.col2num("C")
            measure_col_num = self.col2num("D")

            program_qnodes = (session.query(model.QuestionNode)
                .filter_by(program_id=program_id))

            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aquamark_response_types.json')) as file:
                response_types = json.load(file)
            # session.expunge_all()

            try:
                # for row_num in range(0, 1):
                order = title = ''
                for row_num in range(0, len(all_rows)-1):
                    order, title = self.parse_order_title(all_rows, row_num, "A")
                    function = program_qnodes.filter_by(parent_id=None, title=title).one()
                    log.debug("function: %s", function)
                    function_order = order

                    order, title = self.parse_order_title(all_rows, row_num, "B")
                    process = program_qnodes.filter_by(parent_id=function.id, title=title).one()
                    log.debug("process: %s", process)

                    order, title = self.parse_order_title(all_rows, row_num, "C")
                    subprocess = program_qnodes.filter_by(parent_id=process.id, title=title).one()
                    log.debug("subprocess: %s", subprocess)

                    order, title = self.parse_order_title(all_rows, row_num, "D")
                    measure = [
                        qm.measure for qm in subprocess.qnode_measures
                        if qm.measure.title == title]

                    if len(measure) == 1:
                        measure = measure[0]
                    else:
                        raise Exception("This survey does not match the target survey. ")
                    log.debug("measure: %s", measure)


                    log.debug("measure response_type: %s", measure.response_type.name)

                    response = model.Response()
                    response.program_id = program_id
                    response.survey_id = survey_id
                    response.measure_id = measure.id
                    response.submission_id = submission.id
                    response.user_id = user_id
                    response.comment = all_rows[row_num][self.col2num("K")]
                    response.not_relevant = False # Need to fix this hard coding
                    response.modified = datetime.datetime.utcnow()
                    response.approval = 'draft'
                    response_part = []

                    response_part.append(self.parse_response_type(all_rows, row_num, measure.response_type, "E"))
                    if function_order != "7":
                        response_part.append(self.parse_response_type(all_rows, row_num, measure.response_type, "F"))
                        response_part.append(self.parse_response_type(all_rows, row_num, measure.response_type, "G"))
                        response_part.append(self.parse_response_type(all_rows, row_num, measure.response_type, "H"))
                    response.response_parts  = response_part
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

        return program_id

    def parse_response_type(self, all_rows, row_num, response_type, col_chr):
        response_text = all_rows[row_num][self.col2num(col_chr)]
        index =  ord(col_chr) - ord("E")

        try:
            response_options = [
                r["name"].replace(" ", "").lower()
                for r in response_type.parts[index]["options"]]
        except IndexError:
            raise ImportError(
                "This measure only has %d part(s)" %
                len(response_type.parts))

        try:
            response_index = response_options.index(response_text.replace(" ", "").lower())
        except (AttributeError, ValueError) as e:
            raise ImportError(
                "Response %d: '%s' is not a valid option" %
                (index + 1, response_text))

        return {"index": response_index, "note": response_text}

    CHOICE_PATTERN = re.compile(r'(?P<order>[\s+]) (?P<title>.+)')

    def parse_order_title(self, all_rows, row_num, col_chr, pattern):
        col_num = self.col2num(col_chr)
        cell = all_rows[row_num][col_num]
        match = Importer.CHOICE_PATTERN.match(cell)
        if not match:
            raise ImportError("Could not parse cell %s%s" % (row_num, col_chr))
        order = match.group('order')
        title = match.group('title').replace("\n", chr(10))
        return order, title


    def parse_description(self, all_rows, starting_row_num, prev_column = None, paragraph=None):
        # print("starting_row_num", starting_row_num, "sheet", sheet.nrows)
        if starting_row_num + 1 >= len(all_rows):
            return ""

        if prev_column:
            header_cell = all_rows[starting_row_num + 1][self.col2num("J")]

            if prev_column == header_cell:
                description_cell = all_rows[starting_row_num + 1][self.col2num("K")]
                desc = description_cell
                desc += self.parse_description(all_rows, starting_row_num + 1, prev_column)
                return desc
            else:
                return ""
        else:
            para = all_rows[starting_row_num + 1][self.col2num("I")]
            description_cell = all_rows[starting_row_num + 1][self.col2num("K")]

            if paragraph:
                if para == paragraph:
                    desc = chr(10) + chr(10) + description_cell
                    desc += self.parse_description(all_rows, starting_row_num + 1, None, paragraph=para)
                    return desc
                else:
                    return ""
            else:
                desc = description_cell
                desc += self.parse_description(all_rows, starting_row_num + 1, None, paragraph=para)
                return desc
