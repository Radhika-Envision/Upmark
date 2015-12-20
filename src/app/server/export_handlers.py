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

from sqlalchemy.orm import joinedload, lazyload
from tornado import gen
import tornado.web
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor
from tornado.escape import json_decode, json_encode, url_escape, url_unescape
import numpy

BUF_SIZE = 4096
MAX_WORKERS = 4

log = logging.getLogger('app.export_handler')


class ExportSurveyHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, survey_id, hierarchy_id, extension):
        if extension != 'xlsx':
            raise handlers.MissingDocError(
                "File type not supported: %s" % extension)

        with model.session_scope() as session:
            self.check_browse_survey(session, survey_id, hierarchy_id)

            hierarchy = (session.query(model.Hierarchy)
                         .get((hierarchy_id, survey_id)))
            if survey_id != str(hierarchy.survey_id):
                raise handlers.ModelError(
                    "Survey does not belong to specified program.")

        output_file = 'program_{0}_survey_{1}.xlsx'.format(
            survey_id, hierarchy_id)

        with tempfile.TemporaryDirectory() as tmpdirname:
            output_path = os.path.join(tmpdirname, output_file)
            yield self.background_task(
                output_path, survey_id, hierarchy_id)
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment; filename='
                            + output_file)

            with open(output_path, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    @run_on_executor
    def background_task(self, path, survey_id, hierarchy_id):
        e = Exporter()
        survey_id = e.process_structure_file(path, survey_id, hierarchy_id)


class ExportAssessmentHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, assessment_id, extension):
        if extension != 'xlsx':
            raise handlers.MissingDocError(
                "File type not supported: %s" % extension)

        with model.session_scope() as session:
            assessment = (session.query(model.Assessment)
                          .get(assessment_id))
            if assessment.organisation.id != self.organisation.id:
                self.check_privillege('consultant')
            hierarchy_id = str(assessment.hierarchy_id)
            survey_id = str(assessment.survey_id)
            self.check_browse_survey(session, survey_id, hierarchy_id)

        output_file = 'submission_{0}.xlsx'.format(assessment_id)

        with tempfile.TemporaryDirectory() as tmpdirname:
            output_path = os.path.join(tmpdirname, output_file)
            yield self.background_task(
                output_path, survey_id, hierarchy_id, assessment_id, self.current_user.role)
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment; filename='
                            + output_file)

            with open(output_path, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    @run_on_executor
    def background_task(self, path, survey_id, hierarchy_id,
                        assessment_id, user_role):
        e = Exporter()
        survey_id = e.process_structure_file(
            path, survey_id, hierarchy_id, assessment_id,
            user_role)


class ExportResponseHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self, assessment_id, extension):
        if extension != 'xlsx':
            raise handlers.MissingDocError(
                "File type not supported: %s" % extension)

        with model.session_scope() as session:
            assessment = (session.query(model.Assessment)
                          .get(assessment_id))
            if assessment.organisation.id != self.organisation.id:
                self.check_privillege('consultant')
            hierarchy_id = str(assessment.hierarchy_id)
            survey_id = str(assessment.survey_id)
            self.check_browse_survey(session, survey_id, hierarchy_id)


        output_file = 'submission_response_{0}.xlsx'.format(assessment_id)

        with tempfile.TemporaryDirectory() as tmpdirname:
            output_path = os.path.join(tmpdirname, output_file)
            yield self.background_task(
                output_path, survey_id, hierarchy_id, assessment_id)
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment; filename='
                            + output_file)

            with open(output_path, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    @run_on_executor
    def background_task(self, path, survey_id, hierarchy_id,
                        assessment_id):
        e = Exporter()
        base_url = ("%s://%s" % (self.request.protocol,
                self.request.host,))

        survey_id = e.process_response_file(path, survey_id,
                                            assessment_id, base_url)


class Exporter():

    line = 0

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_structure_file(self, file_name, survey_id, hierarchy_id,
                               assessment_id='', user_role=''):
        """
        Open and write an Excel file
        """
        model.connect_db(os.environ.get('DATABASE_URL'))
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet('Scoring')
        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 100)
        worksheet.set_column(2, 2, 18)
        worksheet.set_column(3, 3, 25)

        with model.session_scope() as session:
            survey = session.query(model.Survey).get(survey_id)
            if survey is None:
                raise Exception("There is no Survey.")

            hierarchy = session.query(model.Hierarchy).get((
                hierarchy_id, survey_id))
            if hierarchy is None:
                raise Exception("There is no Hierarchy.")

            self.response_types = survey._response_types

            prefix = ""

            list1 = session.query(model.QuestionNode).filter(
                model.QuestionNode.survey_id == survey_id,
                model.QuestionNode.hierarchy_id == hierarchy.id).all()

            qnode_list = [{"id": str(item.id),
                           "parent_id": str(item.parent_id),
                           "title": item.title,
                           "description": item.description,
                           "seq": item.seq,
                           "total_weight": item.total_weight}
                          for item in list1]

            list2 = session.query(model.QnodeMeasure).filter(
                model.QnodeMeasure.survey_id == survey_id).all()

            measure_list = [{"measure_id": str(item.measure.id),
                             "qnode_id": str(item.qnode_id),
                             "title": item.measure.title,
                             "intent": item.measure.intent,
                             "inputs": item.measure.inputs,
                             "scenario": item.measure.scenario,
                             "questions": item.measure.questions,
                             "weight": item.measure.weight,
                             "response_type": item.measure.response_type,
                             "seq": item.seq}
                            for item in list2]

            response_list = []
            response_qnode_list = []
            log.debug('Exporting assessment %s of survey %s', assessment_id, survey_id)
            if assessment_id != '':
                responses = (session.query(model.Response)
                             .filter(model.Response.assessment_id == assessment_id,
                                     model.Response.survey_id == survey_id)
                             .all())

                if responses:
                    response_list = [{"measure_id": str(item.measure.id),
                                      "response_parts": item.response_parts,
                                      "weight": item.measure.weight,
                                      "comment": item.comment,
                                      "not_relevant": item.not_relevant,
                                      "score": item.score}
                                     for item in responses]
                response_nodes = session.query(model.ResponseNode)\
                    .filter(model.ResponseNode.assessment_id == assessment_id,
                            model.ResponseNode.survey_id == survey_id).all()
                if response_nodes:
                    response_qnode_list = [{"qnode_id": str(item.qnode.id),
                                            "weight": item.qnode.total_weight,
                                            "score": item.score}
                                           for item in response_nodes]

            self.write_qnode_to_worksheet(session, workbook, worksheet,
                                          qnode_list, response_qnode_list, 
                                          measure_list, response_list,
                                          'None', prefix, 0, user_role)

        workbook.close()

    def write_qnode_to_worksheet(self, session, workbook, worksheet,
                                 qnode_list, response_qnode_list, measure_list, response_list,
                                 parent_id, prefix, depth, user_role):

        filtered = [node for node in qnode_list
                    if node["parent_id"] == parent_id]

        filtered_list = sorted(filtered, key=lambda node: node["seq"])

        format = workbook.add_format()
        format.set_text_wrap()
        format.set_border_color('white')
        format.set_top(1)
        format.set_bold()
        format_percent = workbook.add_format()
        format_percent.set_text_wrap()
        format_percent.set_border_color('white')
        format_percent.set_top(1)
        format_percent.set_num_format(10)
        format2 = workbook.add_format()
        format2.set_font_size(12)
        format2.set_text_wrap()
        format2.set_border_color('white')
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
        format_percent.set_bg_color(depth_colors[depth])

        for qnode in filtered_list:
            response_score = [r for r in response_qnode_list
                              if r["qnode_id"] == qnode["id"]]
            percent = None
            if response_score and response_score[0]["weight"] != 0:
                percent = response_score[0]["score"] / response_score[0]["weight"]

            numbering = prefix + str(qnode["seq"] + 1) + ". "
            worksheet.merge_range("A{0}:B{0}".format(self.line + 1),
                                  numbering + qnode["title"], format)
            # this column should not be displayed for user 'clerk'
            if user_role == 'clerk':
                worksheet.write(self.line, 2, '', format)
                worksheet.write(self.line, 3, '', format_percent)
            else:
                worksheet.write(self.line, 2, qnode["total_weight"], format)
                worksheet.write(self.line, 3, percent, format_percent)

            self.line = self.line + 1
            worksheet.write(self.line, 0, '', format2)
            worksheet.write(self.line, 1, qnode["description"], format2)
            worksheet.write(self.line, 2, '', format2)
            worksheet.write(self.line, 3, '', format2)
            self.line = self.line + 1
            self.write_qnode_to_worksheet(session, workbook, worksheet,
                                          qnode_list, response_qnode_list, 
                                          measure_list, response_list,
                                          qnode["id"], numbering, depth + 1,
                                          user_role)
            self.write_measure_to_worksheet(session, workbook, worksheet,
                                            measure_list, response_list, 
                                            qnode["id"], numbering, user_role)

    def write_measure_to_worksheet(self, session, workbook, worksheet,
                                   measure_list, response_list, qnode_id,
                                   prefix, user_role):

        filtered = [node for node in measure_list
                    if node["qnode_id"] == qnode_id]
        filtered_list = sorted(filtered, key=lambda node: node["seq"])

        format = workbook.add_format()
        format.set_text_wrap()
        format.set_bg_color("#FABF8F")
        format.set_bottom_color('white')
        format.set_bottom(1)
        format_bold_header = workbook.add_format()
        format_bold_header.set_text_wrap()
        format_bold_header.set_bg_color("#FABF8F")
        format_bold_header.set_bottom_color('white')
        format_bold_header.set_bottom(1)
        format_bold_header.set_bold()
        format_percent = workbook.add_format()
        format_percent.set_text_wrap()
        format_percent.set_bg_color("#FABF8F")
        format_percent.set_bottom_color('white')
        format_percent.set_bottom(1)
        format_percent.set_num_format(10)
        format_header = workbook.add_format()
        format_header.set_bg_color("#FFE4E1")
        format_header.set_text_wrap()
        format_header.set_bottom_color('white')
        format_header.set_bottom(1)
        format_end = workbook.add_format()
        format_end.set_text_wrap()
        format_end.set_bg_color("#FABF8F")
        format_end.set_bottom_color('white')
        format_end.set_bottom(1)
        format_header_end = workbook.add_format()
        format_header_end.set_bg_color("#FFE4E1")
        format_header_end.set_bottom_color('white')
        format_header_end.set_bottom(1)
        format_part = workbook.add_format()
        format_part.set_text_wrap()
        format_part.set_bg_color("#CCC0DA")
        format_part.set_bottom_color('white')
        format_part.set_bottom(1)
        format_part_answer = workbook.add_format()
        # format_part_answer.set_text_wrap()
        format_part_answer.set_bg_color("#B1A0C7")
        format_part_answer.set_bottom_color('white')
        format_part_answer.set_bottom(1)
        format_end1 = workbook.add_format()
        format_end1.set_text_wrap()
        format_end1.set_bg_color("#FFFFCC")
        format_end1.set_bottom_color('white')
        format_end1.set_bottom(1)
        format_end2 = workbook.add_format()
        format_end2.set_text_wrap()
        format_end2.set_font_color("white")
        format_end2.set_bg_color("#554529")
        format_end2.set_bottom_color('white')
        format_end2.set_bottom(1)
        format_end3 = workbook.add_format()
        format_end3.set_text_wrap()
        format_end3.set_bg_color("#C4BD97")
        format_end3.set_bottom_color('white')
        format_end3.set_bottom(1)


        for qnode_measure in filtered_list:
            response_types = [type for type in self.response_types
                              if type["id"] == qnode_measure["response_type"]]

            response = [r for r in response_list
                        if r["measure_id"] == qnode_measure["measure_id"]]
            percentage = None
            comment = None
            not_relevant = None
            if response and response[0]["weight"] != 0:
                percentage = response[0]["score"] / response[0]["weight"]
                comment = response[0]["comment"]
                if response[0]["not_relevant"]:
                    not_relevant = "Yes"
                else:
                    not_relevant = "No"

            numbering = prefix + str(qnode_measure["seq"] + 1) + ". "
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(
                self.line, 1, numbering + qnode_measure["title"], format_bold_header)
            # this column should not be displayed for user 'clerk'
            if user_role == 'clerk':
                worksheet.write(self.line, 2, '', format)
                worksheet.write(self.line, 3, '', format_percent)
            else:
                worksheet.write(self.line, 2, qnode_measure["weight"], format)
                worksheet.write(self.line, 3, percentage, format_percent)

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
            worksheet.write(self.line, 0, "questions", format_header)
            worksheet.write(self.line, 1, qnode_measure["questions"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "Comments", format_header_end)
            worksheet.write(self.line, 1, comment, format_end1)
            worksheet.write(self.line, 2, "Not Relevant", format_end2)
            worksheet.write(self.line, 3, not_relevant, format_end3)
            # answer option
            parts_len = len(response_types[0]["parts"])
            index = 0
            for part in response_types[0]["parts"]:
                if 'name' in part:
                    worksheet.write(self.line - parts_len + index, 2,
                                    part["name"], format_part)
                index = index + 1

            measure_response = [r for r in response_list
                                if r["measure_id"] == qnode_measure["measure_id"]]

            index = 0
            if measure_response:
                for part in measure_response[0]["response_parts"]:
                    worksheet.write(self.line - parts_len + index, 3,
                                    "%d - %s" % (part["index"] + 1, part["note"]),
                                    format_part_answer)
                    index = index + 1
            else:
                for i in range(0, parts_len):
                    worksheet.write(self.line - parts_len + index, 3,
                                    '', format_part_answer)
                    index = index + 1

            self.line = self.line + 1

    def process_response_file(self, file_name, survey_id, assessment_id, base_url):
        """
        Open and write an Excel file
        """
        model.connect_db(os.environ.get('DATABASE_URL'))
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet('Response')
        worksheet_metadata = workbook.add_worksheet('Metadata')

        format = workbook.add_format()
        format.set_text_wrap()
        format_no_wrap = workbook.add_format()
        format_comment = workbook.add_format()
        format_comment.set_text_wrap()
        format_percent = workbook.add_format()
        format_percent.set_num_format(10)
        format_no_wrap = workbook.add_format()
        format_comment = workbook.add_format()
        format_percent = workbook.add_format()
        format_percent.set_num_format(10)
        format_date = workbook.add_format({'num_format': 'dd/mmm/yy'})
        url_format = workbook.add_format({
            'font_color': 'blue',
            'underline':  1
        })


        line = 1
        with model.session_scope() as session:
            assessment = session.query(model.Assessment)\
                .get(assessment_id)

            if assessment and \
                assessment.hierarchy and \
                assessment.hierarchy.structure and \
                assessment.hierarchy.structure.get('levels'):

                self.write_metadata(workbook, worksheet_metadata, assessment)
                levels = assessment.hierarchy.structure["levels"]
                level_length = len(levels)
                worksheet.set_column(0, level_length, 50)
                # Find max response number and write to header
                max_len_of_response = max(
                    [len(response.response_parts) 
                        for response in assessment.ordered_responses])
                response_types = [part["parts"] for part in assessment.survey._response_types
                                    if len(part["parts"]) == max_len_of_response][0]
                response_parts = [part['name'] for part in  response_types]

                worksheet.set_column(level_length + 1, 
                    level_length + max_len_of_response + 8, 15)
                worksheet.set_column(level_length + max_len_of_response + 9,
                    level_length + max_len_of_response + 9, 100)

                # Header from heirarchy levels
                self.write_response_header(
                    workbook, worksheet, levels, max_len_of_response,
                    response_parts)

                for response in assessment.ordered_responses:
                    # log.info("response: %s", response.measure.id)
                    qnode = response.measure.get_parent(
                        assessment.hierarchy_id)
                    self.write_qnode(
                        worksheet, qnode, line, format, level_length - 1)

                    qnode_measure = [qm for qm in response.measure.qnode_measures]

                    worksheet.write(
                        line, level_length, str(qnode_measure[0].seq + 1)
                            + ". " + response.measure.title, format)
                    self.write_response_parts(
                        worksheet, response.response_parts, line, format_no_wrap,
                            level_length + 1)
                    score = 0
                    if response.measure.weight != 0:
                        score = response.score / response.measure.weight

                    export_approval_status = ['final', 'reviewed', 'approved']

                    self.write_approval(worksheet, line, 
                                level_length + max_len_of_response, response,
                                response.user, format, format_date)
                    if response.approval in export_approval_status:
                        export_approval_status.remove(response.approval)

                    for approval_status in export_approval_status:
                        res = session.query(model.ResponseHistory).\
                            filter_by(id=response.id, approval=approval_status).\
                            order_by(model.ResponseHistory.modified.desc()).\
                            first()
                        if res:
                            user = session.query(model.AppUser).\
                                filter_by(id=res.user_id).\
                                first()

                            self.write_approval(worksheet, line, 
                                level_length + max_len_of_response, res,
                                user, format, format_date)

                    worksheet.write(line, level_length + max_len_of_response + 7,
                            score, format_percent)
                    worksheet.write(line, level_length + max_len_of_response + 8,
                            qnode.total_weight, format_no_wrap)
                    worksheet.write(line, level_length + max_len_of_response + 9,
                            response.comment, format_comment)

                    url = base_url + "/#/measure/{0}?assessment={1}".format(
                          response.measure.id, assessment.id)

                    worksheet.write_url(line, level_length + max_len_of_response + 10,
                            url, url_format, "Link")
                    line = line + 1

        workbook.close()

    def write_approval(self, worksheet, line, column_num, response, user, 
                       format, format_date):

        pad = None
        if response.approval == 'final':
            pad = 0
        elif response.approval == 'reviewed':
            pad = 2
        elif response.approval == 'approved':
            pad = 4

        if pad is not None:
            worksheet.write(line, column_num + pad + 1,
                    user.name, format)
            worksheet.write(line, column_num + pad + 2,
                    response.modified, format_date)



    def write_metadata(self, workbook, sheet, assessment):
        sheet.set_column(0, 1, 40)

        line = 0
        format = workbook.add_format()
        format.set_text_wrap()
        format_header = workbook.add_format()
        format_header.set_text_wrap()
        format_header.set_bold()
        log.info("assessment: %s", assessment.title)

        sheet.write(line, 0, "Program Name", format_header)
        sheet.write(line, 1, assessment.survey.title, format)
        line = line + 1
        sheet.write(line, 0, "Survey Name", format_header)
        sheet.write(line, 1, assessment.hierarchy.title, format)
        line = line + 1
        sheet.write(line, 0, "Organisation", format_header)
        sheet.write(line, 1, assessment.organisation.name, format)
        line = line + 1
        sheet.write(line, 0, "Submission Name", format_header)
        sheet.write(line, 1, assessment.title, format)
        line = line + 1

    def write_response_header(self, workbook, sheet, levels,
                              max_response, response_parts):
        format = workbook.add_format()
        # format.set_text_wrap()
        format.set_bold()

        for level in levels:
            sheet.write(0, levels.index(level), level["title"], format)
        sheet.write(0, len(levels), "Measure", format)
        for index in range(len(response_parts)):
            sheet.write(0, len(levels) + index + 1, response_parts[index],
                format)
        sheet.write(0, len(levels) + max_response + 1, "Final Report By", format)
        sheet.write(0, len(levels) + max_response + 2, "Final Report Date", format)
        sheet.write(0, len(levels) + max_response + 3, "Review By", format)
        sheet.write(0, len(levels) + max_response + 4, "Reviewed Date", format)
        sheet.write(0, len(levels) + max_response + 5, "Approved By", format)
        sheet.write(0, len(levels) + max_response + 6, "Approved Date", format)

        sheet.write(0, len(levels) + max_response + 7, "Score", format)
        sheet.write(0, len(levels) + max_response + 8, "Weight", format)
        sheet.write(0, len(levels) + max_response + 9, "Comment", format)
        sheet.write(0, len(levels) + max_response + 10, "URL", format)

    def write_qnode(self, sheet, qnode, line, format, col):
        if qnode.parent != None:
            self.write_qnode(sheet, qnode.parent, line, format, col - 1)
        sheet.write(line, col, str(qnode.seq + 1) + ". " + qnode.title, format)

    def write_response_parts(self, sheet, parts, line, format, col):
        if parts != None:
            for part in parts:

                sheet.write(
                    line, col, "%d - %s" % (part["index"] + 1, part["note"]),
                    format)
                col = col + 1
        return col