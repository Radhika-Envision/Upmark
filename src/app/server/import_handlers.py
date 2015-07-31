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
        self.write("Task in progress")
        self.finish()

    @run_on_executor
    def background_task(self, survey_id, file_path):
        i = Importer()
        i.process_file(file_path, survey_id)


class ImportResponseHandler(handlers.BaseHandler):

    @handlers.authz('author')
    def put(self, survey_id):
        pass


class Importer():

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_file(self, path, survey_id):
        """
        Open and read an Excel file
        """
        book = xlrd.open_workbook(path)
        scoring_sheet = book.sheet_by_name("Scoring")

        # # read rows
        all_rows = []
        for row_num in range(0, scoring_sheet.nrows - 1):
            cell = scoring_sheet.row(row_num)
            all_rows.append(cell)
            filter =  scoring_sheet.cell(row_num, self.col2num("S"))

        model.connect_db(os.environ.get('DATABASE_URL'))
        
        with model.session_scope() as session:
            s = session.query(model.Survey).get(survey_id)
            print("survey", s)
            m = session.query(model.Measure).filter_by(survey_id=survey_id).first()
            if m:
                raise Exception("Survey is not empty")
            sp = session.query(model.Subprocess).filter_by(survey_id=survey_id).first()
            if sp:
                raise Exception("Survey is not empty")
            p = session.query(model.Process).filter_by(survey_id=survey_id).first()
            if p:
                raise Exception("Survey is not empty")
            f = session.query(model.Function).filter_by(survey_id=survey_id).first()
            if f:
                raise Exception("Survey is not empty")

            function_title_row = [{"title" : row[self.col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'Function Header" in str(row[self.col2num("S")])]
            process_title_row = [{"title" : row[self.col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'Process Header" in str(row[self.col2num("S")])]
            subprocess_title_row = [{"title" : row[self.col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'SubProcess Header" in str(row[self.col2num("S")])]
            #function_row = [row for row in all_rows]
            for function in function_title_row:
                # print("function:", str(function))
                function_obj = self.parse_cell_title(str(function['title']))
                function_order = function_obj['order']
                function_title = function_obj['title']
                # print("function order:", function_order)
                # print("function title:", function_title)
                # print("function:", function)
                function_description = self.parse_description(scoring_sheet, function['row_num'], "empty")
                # print("function description:", function_description)

                f = model.Function()
                f.survey_id = s.id
                f.title = function_title
                f.seq = int(function_order) - 1
                f.description = function_description
                session.add(f)
                session.flush()

                process_row = [row for row in process_title_row if "{}.".format(function_order) in self.parse_text(row['title'])] 
                for process in process_row:
                    process_obj = self.parse_cell_title(str(process['title']))
                    if process_obj:
                        process_order = parse("{function}.{process}", str(process_obj['order']))['process']
                        process_title = process_obj['title']

                        # print("process order:", process_order)
                        # print("process title:", process_title)
                        process_description = self.parse_description(scoring_sheet, process['row_num'], "empty")
                        # print("process description:", process_description)

                        p = model.Process()
                        p.survey_id = s.id
                        p.function_id = f.id
                        p.title = process_title
                        p.seq = int(process_order) - 1
                        p.description = process_description
                        session.add(p)
                        session.flush()


                        subprocess_row = [row for row in subprocess_title_row if "{}.{}.".format(function_order, process_order) in str(row['title'])] 
                        for subprocess in subprocess_row:
                            subprocess_obj = self.parse_cell_title(str(subprocess['title']))
                            if subprocess_obj:
                                subprocess_order = parse("{function}.{process}.{subprocess}", str(subprocess_obj['order']))['subprocess']
                                subprocess_title = subprocess_obj['title']

                                # print("subprocess order:", subprocess_order)
                                # print("subprocess title:", subprocess_title)
                                subprocess_description = self.parse_description(scoring_sheet, subprocess['row_num'], "empty")
                                # print("subprocess description:", subprocess_description)

                                sp = model.Subprocess()
                                sp.survey_id = s.id
                                sp.process_id = p.id
                                sp.title = subprocess_title
                                sp.seq = int(subprocess_order) - 1
                                sp.description = subprocess_description
                                session.add(sp)
                                session.flush()

                                # for row in all_rows:
                                #     print("row", row[self.col2num("F")])
                                measure_title_row = [{"title" : row[self.col2num("k")], "row_num" : all_rows.index(row), "weight" : row[self.col2num("L")]} 
                                                    for row in all_rows 
                                                    if float(function_order) == self.parse_cell_number(row[self.col2num("C")]) and 
                                                    float(process_order) == self.parse_cell_number(row[self.col2num("D")]) and
                                                    float(subprocess_order) == self.parse_cell_number(row[self.col2num("E")]) and
                                                    self.parse_cell_number(str(row[self.col2num("F")])) != 0 and
                                                    self.parse_cell_number(str(row[self.col2num("G")])) == 1] 


                                for measure in measure_title_row:
                                    measure_obj = self.parse_cell_title(str(measure['title']))
                                    if measure_obj:
                                        measure_order = parse("{function}.{process}.{subprocess}.{measure}", str(measure_obj['order']))['measure']
                                        measure_title = measure_obj['title']

                                        # print("measure order:", measure_order)
                                        # print("measure title:", measure_title)
                                        # print("measure row_num:",  measure['row_num'])

                                        measure_intent = self.parse_description(scoring_sheet, measure['row_num'], "Intent")
                                        measure_inputs = self.parse_description(scoring_sheet, measure['row_num'] + 1, "Iputs")
                                        measure_scenario = self.parse_description(scoring_sheet, measure['row_num'] + 2, "Scenario")
                                        measure_questions = self.parse_description(scoring_sheet, measure['row_num'] + 3, "Questions")
                                        measure_comments = self.parse_description(scoring_sheet, measure['row_num'] + 4, "Comments")
                                        measure_weight = self.parse_cell_number(measure['weight'])

                                        # print("measure measure_intent:", json.dumps(measure_intent))
                                        # print("measure measure_inputs:", measure_inputs)
                                        # print("measure measure_scenario:", measure_scenario)
                                        # print("measure measure_questions:", measure_questions)
                                        # print("measure measure_comments:", measure_comments)

                                        m = model.Measure()
                                        m.survey_id = s.id
                                        m.subprocess_id = sp.id
                                        m.seq = int(measure_order) - 1
                                        m.title = measure_title
                                        m.weight = measure_weight
                                        m.intent = measure_intent
                                        m.inputs = measure_inputs
                                        m.scenario = measure_scenario
                                        m.questions = measure_questions
                                        m.response_type = "Test"
                                        session.add(m)
                                        session.flush()



    def parse_description(self, sheet, starting_row_num, prev_column):
        print("starting_row_num", starting_row_num, "sheet", sheet.nrows)
        if starting_row_num + 1 >= sheet.nrows:
            return ""

        header_cell = str(sheet.cell(starting_row_num + 1, self.col2num("J")))
        desc = ""
        if prev_column in str(header_cell):
            description_cell = sheet.cell(starting_row_num + 1, self.col2num("K"))
            # if prev_column == "Comments":
            desc = self.parse_text(description_cell)
            desc += self.parse_description(sheet, starting_row_num + 1, prev_column)
            return desc
        else:
            return ''


    def parse_cell_title(self, row_text):
        return parse("{order} - {title}", self.parse_text(row_text))

    def parse_text(self, row_text):
        row_text = str(row_text)
        if row_text[:6] == "text:'":
            parse_obj = parse("text:'{text}'", row_text)
        else:
            parse_obj = parse('text:"{text}"', row_text)
        if parse_obj:
            return parse_obj['text']
        return ''


    def parse_cell_number(self, cell):
        value_obj = parse("number:{value}", str(cell))
        if value_obj is None:
            return 0
        return float(value_obj['value'])