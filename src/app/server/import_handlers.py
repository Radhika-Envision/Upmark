import xlrd
import string
import model
import app
import os
from parse import parse
import handlers
import logging
import tempfile
import threading
import json

from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor


MAX_WORKERS = 4

log = logging.getLogger('app.import_handler')


class ImportStructureHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # @handlers.authz('author')
    @gen.coroutine
    def post(self, survey_id):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        fd.write(fileinfo['body'])
        yield self.background_task(survey_id, fd.name)
        self.set_header("Content-Type", "text/plain")
        self.write("Task finished")
        fd.close()
        self.finish()

    @run_on_executor
    def background_task(self, survey_id, file_path):
        i = Importer()
        i.process_structure_file(file_path, survey_id)


class ImportResponseHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # @handlers.authz('author')
    @gen.coroutine
    def post(self, survey_id):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        fd.write(fileinfo['body'])
        yield self.background_task(survey_id, fd.name)
        self.set_header("Content-Type", "text/plain")
        self.write("Task finished")
        fd.close()
        self.finish()

    @run_on_executor
    def background_task(self, survey_id, file_path):
        i = Importer()
        i.process_response_file(file_path, survey_id)


class Importer():

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_structure_file(self, path, survey_id):
        """
        Open and read an Excel file
        """
        book = xlrd.open_workbook(path)
        scoring_sheet = book.sheet_by_name("Scoring")

        # read rows
        all_rows = []
        for row_num in range(0, scoring_sheet.nrows - 1):
            cell = scoring_sheet.row(row_num)
            all_rows.append(cell)
            filter = scoring_sheet.cell(row_num, self.col2num("S"))

        model.connect_db(os.environ.get('DATABASE_URL'))

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            print("survey", survey)
            m = session.query(model.Measure).filter_by(
                survey_id=survey_id).first()
            if m:
                raise Exception("Survey is not empty")
            h = session.query(model.Hierarchy).filter_by(
                survey_id=survey_id).first()
            if h:
                raise Exception("Survey is not empty")
            q = session.query(model.QuestionNode).filter_by(
                survey_id=survey_id).first()
            if q:
                raise Exception("Survey is not empty")

            hierarchy = model.Hierarchy()
            hierarchy.survey_id = survey.id
            hierarchy.title = "Aquamark (Imported)"
            hierarchy.description = "WSAA's own 4-level hierarchy."
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aquamark_hierarchy.json')) as data_file:
                hierarchy.structure = json.load(data_file)
            session.add(hierarchy)
            session.flush()

            log.info("hierarchy: %s" % hierarchy.id)

            function_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'Function Header" in str(row[self.col2num("S")])]
            process_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'Process Header" in str(row[self.col2num("S")])]
            subprocess_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'SubProcess Header" in str(row[self.col2num("S")])]
            #function_row = [row for row in all_rows]
            for function in function_title_row:
                # print("function:", str(function))
                function_obj = self.parse_cell_title(str(function['title']))
                function_order = function_obj['order']
                function_title = function_obj['title']
                # print("function order:", function_order)
                # print("function title:", function_title)
                # print("function:", function)
                function_description = self.parse_description(
                    scoring_sheet, function['row_num'], "empty")
                # log.info("function description: %s" % function_description)
                # log.info("survey_id: %s" % survey.id)
                # log.info("heirarchy_id: %s" % hierarchy.id)
                # log.info("function description: %s" % function_description)
                # log.info("function description: %s" % function_description)

                qnode_function = model.QuestionNode()
                qnode_function.survey_id = survey.id
                qnode_function.hierarchy_id = hierarchy.id
                qnode_function.seq = int(function_order) - 1
                qnode_function.title = function_title
                qnode_function.description = function_description

                session.add(qnode_function)
                session.flush()
                log.info("qnode_function: %s" % qnode_function)

                process_row = [row for row in process_title_row if "{}.".format(
                    function_order) in self.parse_text(row['title'])]
                for process in process_row:
                    process_obj = self.parse_cell_title(str(process['title']))
                    if process_obj:
                        process_order = parse(
                            "{function}.{process}", str(process_obj['order']))['process']
                        process_title = process_obj['title']

                        # print("process order:", process_order)
                        # print("process title:", process_title)
                        process_description = self.parse_description(
                            scoring_sheet, process['row_num'], "empty")
                        log.info("process description: %s" %
                                 process_description)

                        qnode_process = model.QuestionNode()
                        qnode_process.survey_id = survey.id
                        qnode_process.hierarchy_id = hierarchy.id
                        qnode_process.parent_id = qnode_function.id
                        qnode_process.seq = int(process_order) - 1
                        qnode_process.title = process_title
                        qnode_process.description = process_description
                        session.add(qnode_process)
                        session.flush()

                        subprocess_row = [row for row in subprocess_title_row if "{}.{}.".format(
                            function_order, process_order) in str(row['title'])]
                        for subprocess in subprocess_row:
                            subprocess_obj = self.parse_cell_title(
                                str(subprocess['title']))
                            if subprocess_obj:
                                subprocess_order = parse(
                                    "{function}.{process}.{subprocess}", str(subprocess_obj['order']))['subprocess']
                                subprocess_title = subprocess_obj['title']

                                # print("subprocess order:", subprocess_order)
                                # print("subprocess title:", subprocess_title)
                                subprocess_description = self.parse_description(
                                    scoring_sheet, subprocess['row_num'], "empty")
                                log.info("subprocess description: %s" %
                                         subprocess_description)

                                qnode_subprocess = model.QuestionNode()
                                qnode_subprocess.survey_id = survey.id
                                qnode_subprocess.hierarchy_id = hierarchy.id
                                qnode_subprocess.parent_id = qnode_process.id
                                qnode_subprocess.seq = int(
                                    subprocess_order) - 1
                                qnode_subprocess.title = subprocess_title
                                qnode_subprocess.description = subprocess_description

                                session.add(qnode_subprocess)
                                session.flush()

                                # for row in all_rows:
                                #     print("row", row[self.col2num("F")])
                                measure_title_row = [{"title": row[self.col2num("k")], "row_num": all_rows.index(row), "weight": row[self.col2num("L")], "resp_num": row[self.col2num("F")]}
                                                     for row in all_rows
                                                     if float(function_order) == self.parse_cell_number(row[self.col2num("C")]) and
                                                     float(process_order) == self.parse_cell_number(row[self.col2num("D")]) and
                                                     float(subprocess_order) == self.parse_cell_number(row[self.col2num("E")]) and
                                                     self.parse_cell_number(str(row[self.col2num("F")])) != 0 and
                                                     self.parse_cell_number(str(row[self.col2num("G")])) == 1]

                                for measure in measure_title_row:
                                    measure_obj = self.parse_cell_title(
                                        str(measure['title']))
                                    if measure_obj:
                                        measure_order = parse("{function}.{process}.{subprocess}.{measure}", str(
                                            measure_obj['order']))['measure']
                                        measure_title = measure_obj['title']

                                        measure_intent = self.parse_description(
                                            scoring_sheet, measure['row_num'], "Intent")
                                        measure_inputs = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 1, "Inputs")
                                        measure_scenario = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 2, "Scenario")
                                        measure_questions = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 3, "Questions")
                                        # Comments are part of the response, so ignore that row
                                        measure_weight = self.parse_cell_number(
                                            measure['weight'])

                                        m = model.Measure()
                                        m.survey_id = survey.id
                                        m.title = measure_title
                                        m.weight = measure_weight
                                        m.intent = measure_intent
                                        m.inputs = measure_inputs
                                        m.scenario = measure_scenario
                                        m.questions = measure_questions
                                        response_type = "standard"
                                        if function_order == "7":
                                            log.info("business-support: %s", measure['resp_num'])
                                            response_type = "business-support-%s" % int(self.parse_cell_number(measure['resp_num']))
                                        m.response_type = response_type
                                        session.add(m)
                                        session.flush()

                                        qnode_subprocess.measures.append(m)
                                        session.flush()

    def process_response_file(self, path, survey_id):
        """
        Open and read an Excel file
        """
        book = xlrd.open_workbook(path)
        scoring_sheet = book.sheet_by_name("Scoring")

        all_rows = []
        for row_num in range(0, scoring_sheet.nrows - 1):
            cell = scoring_sheet.row(row_num)
            all_rows.append(cell)
            filter = scoring_sheet.cell(row_num, self.col2num("S"))

        model.connect_db(os.environ.get('DATABASE_URL'))

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            hierarchy = session.query(model.Hierarchy).filter_by(survey_id=survey.id).first()

            function_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'Function Header" in str(row[self.col2num("S")])]
            process_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'Process Header" in str(row[self.col2num("S")])]
            subprocess_title_row = [{"title": row[self.col2num("J")], "row_num": all_rows.index(
                row)} for row in all_rows if "'SubProcess Header" in str(row[self.col2num("S")])]

            for function in function_title_row:
                function_obj = self.parse_cell_title(str(function['title']))
                function_order = function_obj['order']
                function_title = function_obj['title']
                function_description = self.parse_description(scoring_sheet, function['row_num'], "empty")

                qnode_function = session.query(model.QuestionNode).filter_by(
                    survey_id=survey_id, hierarchy_id=hierarchy.id, parent_id=None, seq=(int(function_order) - 1)).first()

                if not qnode_function:
                    raise Exception("This file is not match with Survey.")
                if not (qnode_function.title == function_title and qnode_function.description == function_description):
                    raise Exception("This file is not match with Survey.")

                process_row = [row for row in process_title_row if "{}.".format(
                    function_order) in self.parse_text(row['title'])]
                for process in process_row:
                    process_obj = self.parse_cell_title(str(process['title']))
                    if process_obj:
                        process_order = parse("{function}.{process}", str(process_obj['order']))['process']
                        process_title = process_obj['title']

                        process_description = self.parse_description(scoring_sheet, process['row_num'], "empty")
                        qnode_process = session.query(model.QuestionNode).filter_by(
                            survey_id=survey_id, parent_id=qnode_function.id, seq=(int(process_order) - 1)).first()
                        if not qnode_process:
                            raise Exception("This file is not match with Survey.")
                        if not (qnode_process.title == process_title and qnode_process.description == process_description):
                            raise Exception("This file is not match with Survey.")
                        

                        subprocess_row = [row for row in subprocess_title_row if "{}.{}.".format(
                            function_order, process_order) in str(row['title'])]
                        for subprocess in subprocess_row:
                            subprocess_obj = self.parse_cell_title(str(subprocess['title']))
                            if subprocess_obj:
                                subprocess_order = parse(
                                    "{function}.{process}.{subprocess}", str(subprocess_obj['order']))['subprocess']
                                subprocess_title = subprocess_obj['title']

                                subprocess_description = self.parse_description(scoring_sheet, subprocess['row_num'], "empty")

                                qnode_subprocess = session.query(model.QuestionNode).filter_by(
                                    survey_id=survey_id, parent_id=qnode_process.id, seq=(int(subprocess_order) - 1)).first()
                                if not qnode_subprocess:
                                    raise Exception("This file is not match with Survey.")
                                if not (qnode_subprocess.title == subprocess_title and qnode_subprocess.description == subprocess_description):
                                    raise Exception("This file is not match with Survey.")

                                measure_title_row = [{"title": row[self.col2num("k")], "row_num": all_rows.index(row), "weight": row[self.col2num("L")]}
                                                     for row in all_rows
                                                     if float(function_order) == self.parse_cell_number(row[self.col2num("C")]) and
                                                     float(process_order) == self.parse_cell_number(row[self.col2num("D")]) and
                                                     float(subprocess_order) == self.parse_cell_number(row[self.col2num("E")]) and
                                                     self.parse_cell_number(str(row[self.col2num("F")])) != 0 and
                                                     self.parse_cell_number(str(row[self.col2num("G")])) == 1]

                                for measure in measure_title_row:
                                    measure_obj = self.parse_cell_title(
                                        str(measure['title']))
                                    if measure_obj:
                                        measure_order = parse("{function}.{process}.{subprocess}.{measure}", str(
                                            measure_obj['order']))['measure']
                                        measure_title = measure_obj['title']

                                        measure_intent = self.parse_description(
                                            scoring_sheet, measure['row_num'], "Intent")
                                        measure_inputs = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 1, "Inputs")
                                        measure_scenario = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 2, "Scenario")
                                        measure_questions = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 3, "Questions")
                                        measure_comments = self.parse_description(
                                            scoring_sheet, measure['row_num'] + 4, "Comments")
                                        measure_weight = self.parse_cell_number(
                                            measure['weight'])

                                        m = session.query(model.Measure).join(model.QnodeMeasure).filter_by(
                                            survey_id=survey_id, qnode_id=qnode_subprocess.id, 
                                            seq=(int(measure_order) - 1)).first()
                                        if not m:
                                            raise Exception("This file is not match with Survey.")
                                        if not (m.title == measure_title):
                                            raise Exception("This file is not match with Survey.")
                                        
                                        # r = model.Response()
                                        # r.survey_id = survey.id
                                        # r.user_id = self.get_current_user().id
                                        # # r.assessment_id = assement.id
                                        # r.measure_id = m.id
                                        # r.comment = measure_comments
                                        # r.not_relevant = True
                                        # # r.response_parts = measure_parts
                                        # r.audit_reason = audit_reason

                                        session.add(r)
                                        session.flush()

                                        ######## TODO : save response to the database


    def parse_description(self, sheet, starting_row_num, prev_column):
        # print("starting_row_num", starting_row_num, "sheet", sheet.nrows)
        if starting_row_num + 1 >= sheet.nrows:
            return ""

        header_cell = str(sheet.cell(starting_row_num + 1, self.col2num("J")))
        desc = ""
        if prev_column in str(header_cell):
            description_cell = sheet.cell(
                starting_row_num + 1, self.col2num("K"))
            # if prev_column == "Comments":
            desc = self.parse_text(description_cell)
            desc += self.parse_description(sheet,
                                           starting_row_num + 1, prev_column)
            return desc
        else:
            return ''

    def parse_cell_title(self, row_text):
        return parse("{order} - {title}", self.parse_text(row_text))

    def parse_text(self, row_text):
        row_text = str(row_text)
        if row_text[:6] == "text:'":
            parse_obj = parse("text:'{value}'", row_text)
        else:
            parse_obj = parse('text:"{value}"', row_text)
        if parse_obj:
            return parse_obj['value'].replace('\\n', chr(ord('\n')))
        return ''

    def parse_cell_number(self, cell):
        value_obj = parse("number:{value}", str(cell))
        if value_obj is None:
            return 0
        return float(value_obj['value'])
