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
import datetime
import xlsxwriter 

from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor


MAX_WORKERS = 4

log = logging.getLogger('app.export_handler')


class ExportStructureHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @handlers.authz('author')
    def get(self, survey_id):
        output_file = 'export_{}.xlsx'.format(survey_id)
        if os.path.exists(output_file):
            os.remove(output_file)

        self.background_task(survey_id)
        buf_size = 4096
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition', 'attachment; filename=' + output_file)
        with open(output_file, 'rb') as f:
            while True:
                data = f.read(buf_size)
                if not data:
                    break
                self.write(data)
        self.finish()

    def background_task(self, survey_id):
        e = Exporter()
        survey_id = e.process_structure_file(survey_id)


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
        i = Exporter()
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
        i = Exporter()
        survey_id = self.get_argument('survey')
        organisation_id = self.get_argument('organisation')
        hierarchy_id = self.get_argument("hierarchy")
        title = self.get_argument('title')
        user_id = self.get_current_user().id
        survey_id = i.process_assessment_file(
                        file_path, 
                        survey_id, 
                        hierarchy_id, 
                        organisation_id, 
                        title, 
                        user_id)
        return survey_id


class Exporter():

    line = 0

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_structure_file(self, survey_id):
        """
        Open and read an Excel file
        """
        model.connect_db(os.environ.get('DATABASE_URL'))
        workbook = xlsxwriter.Workbook("export_{}.xlsx".format(survey_id))
        worksheet = workbook.add_worksheet('Scoring')
        worksheet.set_column(0, 0, 100) 
        worksheet.set_column(1, 1, 200) 

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            if survey is None:
                raise Exception("There is no Survey.")

            hierarchy = session.query(model.Hierarchy).get((
                survey.hierarchies[0].id, survey_id))
            hierarchy = session.query(model.Hierarchy).filter(
                model.Hierarchy.survey_id==survey_id).first()
            if hierarchy is None:
                raise Exception("There is no Hierarchy.")

            prefix = ""
            self.write_qnode_to_worksheet(session, workbook, worksheet, survey_id, 
                hierarchy.id, None, prefix, 0)

        workbook.close()
        log.info("Process finished")

    def write_qnode_to_worksheet(self, session, workbook, worksheet, 
                survey_id, hierarchy_id, parent_id, prefix, depth):

        query = session.query(model.QuestionNode).filter(
                        model.QuestionNode.survey_id==survey_id,
                        model.QuestionNode.hierarchy_id==hierarchy_id, 
                        model.QuestionNode.parent_id==parent_id)
        query = query.order_by(model.QuestionNode.seq.asc())

        format = workbook.add_format()
        if depth == 0:
            format.set_font_size(14)
            format.set_bg_color("blue")
        elif depth == 1:
            format.set_font_size(12)
            format.set_bg_color("red")
        elif depth == 2:
            format.set_font_size(12)
            format.set_bg_color("green")
        elif depth == 3:
            format.set_font_size(12)
            format.set_bg_color("organge")
        else:
            format.set_font_size(11)
            format.set_bg_color("organge")

        for qnode in query.all():
            numbering = prefix + str(qnode.seq + 1) + ". "
            worksheet.write(self.line, 0, numbering + qnode.title, format)
            self.line = self.line + 1
            format.set_font_size(12)
            worksheet.write(self.line, 1, qnode.description, format)
            self.line = self.line + 1
            self.write_qnode_to_worksheet(session, workbook, worksheet, 
                survey_id, hierarchy_id, qnode.id, numbering, depth + 1)
            self.write_measure_to_worksheet(session, workbook, worksheet, 
                survey_id, qnode.id, numbering)

    def write_measure_to_worksheet(self, session, workbook, worksheet, 
                survey_id, qnode_id, prefix):
        query = session.query(model.QnodeMeasure).filter(
                        model.QnodeMeasure.survey_id==survey_id,
                        model.QnodeMeasure.qnode_id==qnode_id)
        query = query.order_by(model.QnodeMeasure.seq.asc())

        for qnode_measure in query.all():
            format = workbook.add_format()
            format.set_text_wrap()
            numbering = prefix + str(qnode_measure.seq + 1) + ". "
            worksheet.write(self.line, 1, numbering + qnode_measure.measure.title, format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "intent")
            row_len = qnode_measure.measure.intent.count('\n') + 1
            worksheet.set_row(self.line, 20 * row_len, None)
            worksheet.write(self.line, 1, qnode_measure.measure.intent, format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "inputs")
            worksheet.write(self.line, 1, qnode_measure.measure.inputs, format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "scenario")
            worksheet.write(self.line, 1, qnode_measure.measure.scenario, format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "questions")
            worksheet.write(self.line, 1, qnode_measure.measure.questions, format)
            self.line = self.line + 1

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
                    log.info("function: %s", function)
                    function_order = order

                    order, title = self.parse_order_title(all_rows, row_num, "B", "{order} {title}")
                    process = survey_qnodes.filter_by(parent_id=function.id, title=title).one()
                    log.info("process: %s", process)

                    order, title = self.parse_order_title(all_rows, row_num, "C", "{order} {title}")
                    subprocess = survey_qnodes.filter_by(parent_id=process.id, title=title).one()
                    log.info("subprocess: %s", subprocess)

                    order, title = self.parse_order_title(all_rows, row_num, "D", "{order} {title}")
                    measure = [m for m in subprocess.measures if m.title == title]

                    if len(measure) == 1:
                        measure = measure[0]
                    else:
                        raise Exception("This survey is not matching current open survey. ")
                    log.info("measure: %s", measure)
        

                    log.info("measure response_type: %s", [r for r in response_types if r["id"] == measure.response_type][0])
                    r_types = [r for r in response_types if r["id"] == measure.response_type][0]

                    response = model.Response()
                    response.survey_id = survey_id
                    response.measure_id = measure.id
                    response.assessment_id = assessment.id
                    response.user_id = user_id
                    response.comment = all_rows[row_num][self.col2num("K")]
                    response.not_relevant = False # Need to fix this hard coding
                    response.modified = datetime.datetime.utcnow()
                    response.approval = 'draft'
                    response_part = []

                    response_part.append(self.parse_response_type(all_rows, row_num, r_types, "E"))
                    if function_order != "7":
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "F"))
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "G"))
                        response_part.append(self.parse_response_type(all_rows, row_num, r_types, "H"))
                    response.response_parts  = response_part
                    response.audit_reason = "Import"
                    # response.attachments = None
                    session.add(response)
            except sqlalchemy.orm.exc.NoResultFound:
                raise Exception("This survey is not matching current open survey. ", all_rows[row_num], title)

            assessment.update_stats_descendants()

        return survey_id

    def parse_response_type(self, all_rows, row_num, types, col_chr):
        response_text = all_rows[row_num][self.col2num(col_chr)]
        index =  ord(col_chr) - ord("E")
        response_options = [r["name"].replace(" ", "").lower() for r in types["parts"][index]["options"]]
        response_index = response_options.index(response_text.replace(" ", "").lower())
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
