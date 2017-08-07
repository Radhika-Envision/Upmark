import json
import logging
import os
import tempfile
import xlrd

import bleach
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


MAX_WORKERS = 4

log = logging.getLogger('app.importer.prog_import')


class ImportStructureHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        request_son = denormalise(json_decode(self.get_argument('program')))
        surveygroup_ids = [sg.id for sg in request_son.surveygroups]

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
            all_rows = self.read_sheet(fd.name)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = model.Program()
            program.title = title
            program.description = bleach.clean(description, strip=True)
            session.add(program)

            surveygroups = (
                session.query(model.SurveyGroup)
                .filter(model.SurveyGroup.id.in_(surveygroup_ids))
                .all())
            if not len(surveygroups) == len(surveygroup_ids):
                raise errors.ModelError(
                    "Some surveygroups could not be found")
            program.surveygroups = set(surveygroups)

            session.flush()
            program_id = program.id

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_add')

            self.process_structure_file(all_rows, session, program)

        return program_id

    def read_sheet(self, path):
        with xlrd.open_workbook(path) as book:
            sheet = book.sheet_by_name("Scoring")
            all_rows = [
                sheet.row_values(row_i)
                for row_i in range(0, sheet.nrows - 1)]
        return all_rows

    def process_structure_file(self, all_rows, session, program):
        response_types = self.create_response_types(session, program)

        survey = model.Survey()
        survey.program = program
        survey.title = "Imported Survey"
        survey.description = None
        with open(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'aquamark_hierarchy.json')) as data_file:
            survey.structure = json.load(data_file)
        session.add(survey)
        session.flush()

        log.info("survey: %s" % survey.id)

        function_title_row = [{
            "title": row[col2num("J")],
            "order": row[col2num("C")],
            "row_num": all_rows.index(row)
        } for row in all_rows
            if str(row[col2num("S")]) == "Function Header"]

        process_title_row = [{
            "title": row[col2num("J")],
            "order": row[col2num("D")],
            "row_num": all_rows.index(row)
        } for row in all_rows
            if str(row[col2num("S")]) == "Process Header"]

        subprocess_title_row = [{
            "title": row[col2num("J")],
            "order": row[col2num("E")],
            "row_num": all_rows.index(row)
        } for row in all_rows
            if str(row[col2num("S")]) == "SubProcess Header"]

        for function in function_title_row:
            function_order = int(function['order'])
            function_title = function['title'].replace("{} - ".format(
                function_order), "")
            function_description = self.parse_description(
                all_rows, function['row_num'])

            qnode_function = model.QuestionNode()
            qnode_function.program = program
            qnode_function.survey = survey
            qnode_function.seq = function_order - 1
            qnode_function.title = function_title
            qnode_function.description = bleach.clean(
                function_description, strip=True)

            session.add(qnode_function)
            session.flush()

            process_row = [
                row for row in process_title_row
                if "{}.".format(function_order) in row['title']]

            for process in process_row:
                process_order = int(process['order'])
                process_title = process['title'].replace(
                    "{}.{} - ".format(function_order, process_order), "")

                # print("process order:", process_order)
                # print("process title:", process_title)
                process_description = self.parse_description(
                    all_rows, process['row_num'], "")

                qnode_process = model.QuestionNode()
                qnode_process.program = program
                qnode_process.survey = survey
                qnode_process.parent = qnode_function
                qnode_process.seq = process_order - 1
                qnode_process.title = process_title
                qnode_process.description = bleach.clean(
                    process_description, strip=True)
                # log.info("qnode_process: %s" % qnode_process)
                session.add(qnode_process)
                session.flush()

                subprocess_row = [
                    row for row in subprocess_title_row
                    if "{}.{}.".format(
                        function_order, process_order) in row['title']]
                for subprocess in subprocess_row:
                    subprocess_order = int(subprocess['order'])
                    subprocess_title = subprocess['title'].replace(
                        "{}.{}.{} - ".format(
                            function_order, process_order,
                            subprocess_order),
                        "")

                    # print("subprocess order:", subprocess_order)
                    # print("subprocess title:", subprocess_title)
                    subprocess_description = self.parse_description(
                        all_rows, subprocess['row_num'], "")

                    qnode_subprocess = model.QuestionNode()
                    qnode_subprocess.program = program
                    qnode_subprocess.survey = survey
                    qnode_subprocess.parent = qnode_process
                    qnode_subprocess.seq = subprocess_order - 1
                    qnode_subprocess.title = subprocess_title
                    qnode_subprocess.description = bleach.clean(
                        subprocess_description, strip=True)

                    session.add(qnode_subprocess)
                    session.flush()

                    measure_title_row = [
                        {
                            "title": row[col2num("k")],
                            "row_num": all_rows.index(row),
                            "order": row[col2num("F")],
                            "weight": row[col2num("L")],
                            "resp_num": row[col2num("F")]
                        }
                        for row in all_rows
                        if function_order == row[col2num("C")] and
                        process_order == row[col2num("D")] and
                        subprocess_order == row[col2num("E")] and
                        row[col2num("F")] != 0 and
                        row[col2num("G")] == 1]

                    for measure in measure_title_row:
                        measure_order = int(measure["order"])
                        measure_title = measure['title'].replace(
                            "{}.{}.{}.{} - ".format(
                                function_order, process_order,
                                subprocess_order, measure_order),
                            "")

                        measure_description = self.parse_description(
                            all_rows, measure['row_num'], "Description")
                        # Comments are part of the response, so ignore that
                        # row
                        measure_weight = measure['weight']

                        m = model.Measure()
                        m.program = program
                        m.title = measure_title
                        m.weight = measure_weight
                        m.description = bleach.clean(
                            measure_description, strip=True)
                        rt_id = "standard"
                        if function_order == 7:
                            rt_id = "business-support-%s" % int(
                                measure['resp_num'])
                        # log.info("response_type: %s", rt_id)
                        m.response_type = response_types[rt_id]
                        session.add(m)
                        session.flush()
                        qnode_measure = model.QnodeMeasure(
                            program=program, survey=survey,
                            qnode=qnode_subprocess, measure=m)
                        qnode_subprocess.qnode_measures.reorder()
                        session.add(qnode_measure)
                        session.flush()

        calculator = Calculator.structural()
        calculator.mark_entire_survey_dirty(survey)
        calculator.execute()

    def create_response_types(self, session, program):
        response_types = {}
        with open(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'aquamark_response_types.json')) as file:
            rt_defs = json.load(file)
            for rt_def in rt_defs:
                response_type = model.ResponseType(
                    program=program,
                    name=rt_def['name'],
                    parts=rt_def['parts'],
                    formula=rt_def.get('formula'))
                session.add(response_type)
                log.info("Added RT %s", rt_def['id'])
                response_types[rt_def['id']] = response_type

        return response_types

    def parse_description(
            self, all_rows, starting_row_num, prev_column=None,
            paragraph=None):
        # print("starting_row_num", starting_row_num, "sheet", sheet.nrows)
        if starting_row_num + 1 >= len(all_rows):
            return ""

        if prev_column:
            header_cell = all_rows[starting_row_num + 1][col2num("J")]

            if prev_column == header_cell:
                description_cell = all_rows[starting_row_num + 1][
                    col2num("K")]
                desc = description_cell
                desc += self.parse_description(
                    all_rows, starting_row_num + 1, prev_column)
                return desc
            else:
                return ""
        else:
            para = all_rows[starting_row_num + 1][col2num("I")]
            description_cell = all_rows[starting_row_num + 1][
                col2num("K")]

            if paragraph:
                if para == paragraph:
                    desc = chr(10) + chr(10) + description_cell
                    desc += self.parse_description(
                        all_rows, starting_row_num + 1, None, paragraph=para)
                    return desc
                else:
                    return ""
            else:
                desc = description_cell
                desc += self.parse_description(
                    all_rows, starting_row_num + 1, None, paragraph=para)
                return desc
