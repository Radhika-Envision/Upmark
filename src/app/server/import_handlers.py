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
import sqlalchemy

from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor


MAX_WORKERS = 4

log = logging.getLogger('app.import_handler')


class ImportStructureHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @handlers.authz('author')
    @gen.coroutine
    def post(self):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        try:
            fd.write(fileinfo['body'])
            survey_id = yield self.background_task(fd.name)
        finally:
            fd.close()
        self.set_header("Content-Type", "text/plain")
        self.write(survey_id)
        self.finish()

    @run_on_executor
    def background_task(self, file_path):
        i = Importer()
        title = self.get_argument('title')
        description = self.get_argument('description')
        survey_id = i.process_structure_file(file_path, title, description)
        return survey_id


class ImportResponseHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @handlers.authz('author')
    @gen.coroutine
    def post(self, survey_id):
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


class ImportAssessmentHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @handlers.authz('author')
    @gen.coroutine
    def post(self):
        fileinfo = self.request.files['file'][0]
        fd = tempfile.NamedTemporaryFile()
        try:
            fd.write(fileinfo['body'])
            survey_id = yield self.background_task(fd.name)
        finally:
            fd.close()
        self.set_header("Content-Type", "text/plain")
        self.write(survey_id)
        self.finish()

    @run_on_executor
    def background_task(self, file_path):
        i = Importer()
        survey_id = self.get_argument('survey')
        organisation_id = self.get_argument('organisation')
        hierarchy_id = self.get_argument("hierarchy")
        title = self.get_argument('title')
        user_id = self.get_current_user().id
        survey_id = i.process_assessment_file(file_path, survey_id, hierarchy_id, organisation_id, title, user_id)
        return survey_id


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

            survey = model.Survey()
            survey.title = title
            survey.description = description
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aquamark_response_types.json')) as file:
                survey.response_types = json.load(file)
            session.add(survey)
            session.flush()
            survey_id = str(survey.id)

            hierarchy = model.Hierarchy()
            hierarchy.survey_id = survey.id
            hierarchy.title = "Aquamark (Imported)"
            hierarchy.description = "WSAA's own 4-level hierarchy."
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aquamark_hierarchy.json')) as data_file:
                hierarchy.structure = json.load(data_file)
            session.add(hierarchy)
            session.flush()

            log.info("hierarchy: %s" % hierarchy.id)

            function_title_row = [{"title": row[self.col2num("J")], 
                                   "order": row[self.col2num("C")],
                                   "row_num": all_rows.index(row)} 
                                   for row in all_rows if str(row[self.col2num("S")]) == "Function Header"]
            process_title_row = [{"title": row[self.col2num("J")],
                                  "order": row[self.col2num("D")], 
                                  "row_num": all_rows.index(row)} 
                                  for row in all_rows if str(row[self.col2num("S")]) == "Process Header"]
            subprocess_title_row = [{"title": row[self.col2num("J")], 
                                     "order": row[self.col2num("E")], 
                                     "row_num": all_rows.index(row)} 
                                     for row in all_rows if str(row[self.col2num("S")]) == "SubProcess Header"]


            for function in function_title_row:
                function_order = int(function['order'])
                function_title = function['title'].replace("{} - ".format(
                    function_order), "")
                function_description = self.parse_description(
                    all_rows, function['row_num'])

                qnode_function = model.QuestionNode()
                qnode_function.survey_id = survey.id
                qnode_function.hierarchy_id = hierarchy.id
                qnode_function.seq = function_order - 1
                qnode_function.title = function_title
                qnode_function.description = function_description

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
                    qnode_process.survey_id = survey.id
                    qnode_process.hierarchy_id = hierarchy.id
                    qnode_process.parent_id = qnode_function.id
                    qnode_process.seq = process_order - 1
                    qnode_process.title = process_title
                    qnode_process.description = process_description
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
                        qnode_subprocess.survey_id = survey.id
                        qnode_subprocess.hierarchy_id = hierarchy.id
                        qnode_subprocess.parent_id = qnode_process.id
                        qnode_subprocess.seq = subprocess_order - 1
                        qnode_subprocess.title = subprocess_title
                        qnode_subprocess.description = subprocess_description

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

                            measure_intent = self.parse_description(
                                all_rows, measure['row_num'], "Intent")
                            measure_inputs = self.parse_description(
                                all_rows, measure['row_num'] + 1, "Inputs")
                            measure_scenario = self.parse_description(
                                all_rows, measure['row_num'] + 2, "Scenario")
                            measure_questions = self.parse_description(
                                all_rows, measure['row_num'] + 3, "Questions")
                            # Comments are part of the response, so ignore that row
                            measure_weight = measure['weight']

                            m = model.Measure()
                            m.survey_id = survey.id
                            m.title = measure_title
                            m.weight = measure_weight
                            m.intent = measure_intent
                            m.inputs = measure_inputs
                            m.scenario = measure_scenario
                            m.questions = measure_questions
                            response_type = "standard"
                            if function_order == 7:
                                response_type = "business-support-%s" % int(measure['resp_num'])
                            # log.info("response_type: %s", response_type)
                            m.response_type = response_type
                            session.add(m)
                            session.flush()
                            qnode_subprocess.measures.append(m)
                            session.flush()
            survey.update_stats_descendants()
            return survey_id

    def process_response_file(self, path, survey_id):
        """
        Open and read an Excel file
        """
        book = xlrd.open_workbook(path)
        scoring_sheet = book.sheet_by_name("Scoring")
        '''
        TODO : process response
        '''

    def process_assessment_file(self, path, survey_id, hierarchy_id, organisation_id, title, user_id):
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
            survey = session.query(model.Survey).get(survey_id)
            if survey is None:
                raise Exception("There is no Survey.")

            hierarchy = session.query(model.Hierarchy).filter_by(id=hierarchy_id).one()
            if hierarchy is None:
                raise Exception("There is no Hierarchy.")

            assessment = model.Assessment()
            assessment.survey_id = survey.id
            assessment.hierarchy_id = hierarchy.id
            assessment.organisation_id = organisation_id
            assessment.title = title
            assessment.approval = 'draft'
            session.add(assessment)
            session.flush()

            all_rows = []
            for row_num in range(1, sheet.nrows - 1):
                cell = sheet.row_values(row_num)
                all_rows.append(cell)

            function_col_num = self.col2num("A")
            process_col_num = self.col2num("B")
            subprocess_col_num = self.col2num("C")
            measure_col_num = self.col2num("D")

            survey_qnodes = session.query(model.QuestionNode).filter_by(survey_id=survey_id)

            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aquamark_response_types.json')) as file:
                response_types = json.load(file)
            # session.expunge_all()

            try:
                # for row_num in range(0, 1):
                for row_num in range(0, len(all_rows)-1):
                    order, title = self.parse_order_title(all_rows, row_num, "A", "{order} {title}")
                    function = survey_qnodes.filter_by(parent_id=None, title=title).one()
                    function_order = order

                    order, title = self.parse_order_title(all_rows, row_num, "B", "{order} {title}")
                    process = survey_qnodes.filter_by(parent_id=function.id, title=title).one()

                    order, title = self.parse_order_title(all_rows, row_num, "C", "{order} {title}")
                    subprocess = survey_qnodes.filter_by(parent_id=process.id, title=title).one()

                    order, title = self.parse_order_title(all_rows, row_num, "D", "{order} {title}")
                    measure = [m for m in subprocess.measures if m.title == title]

                    if len(measure) == 1:
                        measure = measure[0]
                    else:
                        raise Exception("This survey is not matching current open survey. ")
        

                    log.info("measure response_type: %s", [r for r in response_types if r["id"] == measure.response_type][0])
                    r_types = [r for r in response_types if r["id"] == measure.response_type][0]

                    response = model.Response()
                    response.survey_id = survey_id
                    response.measure_id = measure.id
                    response.assessment_id = assessment.id
                    response.user_id = user_id
                    response.comment = all_rows[row_num][self.col2num("K")]
                    response.not_relevant = False # Need to fix this hard coding
                    response_part = []

                    response_part.append(self.parse_response_type(all_rows, row_num, r_types, "E"))
                    if function_order != "7":
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "F"))
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "G"))
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "H"))
                    response.response_parts  = response_part
                    response.audit_reason = "Import"
                    response.attachments = None
                    session.add(response)
            except sqlalchemy.orm.exc.NoResultFound:
                raise Exception("This survey is not matching current open survey. ", all_rows[row_num], title)

        return survey_id

    def parse_response_type(self, all_rows, row_num, types, col_chr):
        response_text = all_rows[row_num][self.col2num(col_chr)]
        index =  ord(col_chr) - ord("E")
        response_options = [r["name"] for r in types["parts"][index]["options"]]
        response_index = response_options.index(response_text)
        return {"index": response_index, "note": response_text}


    def parse_order_title(self, all_rows, row_num, col_chr, parse_expression):
        col_num = self.col2num(col_chr)
        column = all_rows[row_num][col_num]
        column_object = parse(parse_expression, column)
        order = column_object["order"]
        title = column_object["title"].replace("\n", chr(10))
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
