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
        worksheet.set_column(0, 0, 20) 
        worksheet.set_column(1, 1, 250) 

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            if survey is None:
                raise Exception("There is no Survey.")

            hierarchy = session.query(model.Hierarchy).get((
                survey.hierarchies[0].id, survey_id))
            if hierarchy is None:
                raise Exception("There is no Hierarchy.")

            prefix = ""

            list = session.query(model.QuestionNode).filter(
                        model.QuestionNode.survey_id==survey_id,
                        model.QuestionNode.hierarchy_id==hierarchy.id).all()

            qnode_list = [{"id" : str(item.id),
                                   "parent_id" : str(item.parent_id), 
                                   "title" : item.title, 
                                   "description" : item.description, 
                                   "seq" : item.seq, 
                                   "total_weight" : item.total_weight}
                             for item in list]

            list2 = session.query(model.QnodeMeasure).filter(
                        model.QnodeMeasure.survey_id==survey_id).all()


            measure_list = [{"qnode_id" : str(item.qnode_id), 
                                   "title" : item.measure.title, 
                                   "intent" : item.measure.intent, 
                                   "inputs" : item.measure.inputs, 
                                   "scenario" : item.measure.scenario, 
                                   "questions" : item.measure.questions,
                                    "seq" : item.seq}
                             for item in list2]

 
            self.write_qnode_to_worksheet(session, workbook, worksheet, 
                qnode_list, measure_list, 'None', prefix, 0)

        workbook.close()

    def write_qnode_to_worksheet(self, session, workbook, worksheet, 
                qnode_list, measure_list, parent_id, prefix, depth):

        # 
        filtered = [node for node in qnode_list 
                         if node["parent_id"] == parent_id]

        filtered_list = sorted(filtered, key=lambda node: node["seq"])


        format = workbook.add_format()
        format.set_text_wrap()
        format.set_top_color('black')
        format.set_top(1)
        format2 = workbook.add_format()
        format2.set_font_size(12)
        format2.set_text_wrap()
        format2.set_top_color('black')
        format2.set_bottom(1)


        depth_colors = ["#4F81BD", "#C0504D", "#9BBB59", "#FABF8F"]
        if depth == 0:
            format.set_font_size(14)
        elif depth == 1:
            format.set_font_size(12)
        elif depth == 2:
            format.set_font_size(12)
        elif depth == 3:
            format.set_font_size(12)
        else:
            format.set_font_size(11)

        format.set_bg_color(depth_colors[depth])
        format2.set_bg_color(depth_colors[depth])

        for qnode in filtered_list:
            log.info("qnode: %s", qnode)
            numbering = prefix + str(qnode["seq"] + 1) + ". "
            worksheet.merge_range("A{0}:B{0}".format(self.line + 1), 
                numbering + qnode["title"], format)
            worksheet.write(self.line, 2, qnode["total_weight"], format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, '', format2)
            worksheet.write(self.line, 1, qnode["description"], format2)
            worksheet.write(self.line, 2, '', format2)
            self.line = self.line + 1
            self.write_qnode_to_worksheet(session, workbook, worksheet, 
                qnode_list, measure_list, qnode["id"], numbering, depth + 1)
            self.write_measure_to_worksheet(session, workbook, worksheet, 
                measure_list, qnode["id"], numbering)

    def write_measure_to_worksheet(self, session, workbook, worksheet, 
                measure_list, qnode_id, prefix):

        filtered = [node for node in measure_list 
                         if node["qnode_id"] == qnode_id]
        filtered_list = sorted(filtered, key=lambda node: node["seq"])

        format = workbook.add_format()
        format.set_text_wrap()
        format.set_bg_color("#FABF8F")
        format.set_bottom_color('white')
        format.set_bottom(1)
        format_header = workbook.add_format()
        format_header.set_bg_color("#FFE4E1")
        format_header.set_bottom_color('white')
        format_header.set_bottom(1)
        format_end = workbook.add_format()
        format_end.set_text_wrap()
        format_end.set_bg_color("#FABF8F")
        format_end.set_bottom_color('black')
        format_end.set_bottom(1)
        format_header_end = workbook.add_format()
        format_header_end.set_bg_color("#FFE4E1")
        format_header_end.set_bottom_color('black')
        format_header_end.set_bottom(1)


        for qnode_measure in filtered_list:

            numbering = prefix + str(qnode_measure["seq"] + 1) + ". "
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(self.line, 1, numbering + qnode_measure["title"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "intent", format_header)
            worksheet.write(self.line, 1, qnode_measure["intent"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "inputs", format_header)
            worksheet.write(self.line, 1, qnode_measure["inputs"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "scenario", format_header)
            worksheet.write(self.line, 1, qnode_measure["scenario"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "questions", format_header_end)
            worksheet.write(self.line, 1, qnode_measure["questions"], format_end)
            worksheet.write(self.line, 2, '', format_end)
            self.line = self.line + 1
