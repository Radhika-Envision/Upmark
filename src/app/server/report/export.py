import logging
import string

import xlsxwriter

import errors
import model


log = logging.getLogger('app.report.export')


class Exporter:

    line = 0

    def col2num(self, col):
        num = 0
        for c in col:
            if c in string.ascii_letters:
                num = num * 26 + (ord(c.upper()) - ord('A'))
        return num

    def process_nested(
            self, file_name, program_id, survey_id, submission_id,
            user_role, base_url):
        """
        Open and write an Excel file
        """
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet('Scoring')
        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 100)
        worksheet.set_column(2, 2, 18)
        worksheet.set_column(3, 3, 25)

        with model.session_scope() as session:
            program = session.query(model.Program).get(program_id)
            if program is None:
                raise errors.MissingDocError("No such program")
            elif program.deleted:
                raise errors.MissingDocError("That program has been deleted")

            survey = session.query(model.Survey).get((
                survey_id, program_id))
            if survey is None:
                raise errors.MissingDocError("No such survey")
            elif survey.deleted:
                raise errors.MissingDocError("That survey has been deleted")

            prefix = ""

            list1 = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.program_id == program_id,
                        model.QuestionNode.survey_id == survey.id,
                        model.QuestionNode.deleted == False)
                .all())

            qnode_list = [{"id": str(item.id),
                           "parent_id": str(item.parent_id),
                           "title": item.title,
                           "description": item.description,
                           "seq": item.seq,
                           "total_weight": item.total_weight}
                          for item in list1]

            list2 = session.query(model.QnodeMeasure).filter(
                model.QnodeMeasure.program_id == program_id).all()

            measure_list = [{"measure_id": str(item.measure.id),
                             "qnode_id": str(item.qnode_id),
                             "title": item.measure.title,
                             "description": item.measure.description,
                             "weight": item.measure.weight,
                             "response_type": item.measure.response_type,
                             "seq": item.seq}
                            for item in list2]

            response_list = []
            response_qnode_list = []
            log.debug('Exporting submission %s of program %s', submission_id, program_id)
            if submission_id != '':
                responses = (session.query(model.Response)
                             .filter(model.Response.submission_id == submission_id)
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
                    .filter(model.ResponseNode.submission_id == submission_id,
                            model.ResponseNode.program_id == program_id).all()
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

    def write_qnode_to_worksheet(
            self, session, workbook, worksheet,
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

            # Hide some data from certain users
            if user_role in {'clerk', 'org_admin'}:
                weight = None
            else:
                weight = qnode['total_weight']

            if user_role == 'clerk':
                score = None
            else:
                score = percent

            worksheet.write(self.line, 2, weight, format)
            worksheet.write(self.line, 3, score, format_percent)

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
            response = [r for r in response_list
                        if r["measure_id"] == qnode_measure["measure_id"]]
            if response:
                response = response[0]
            else:
                response = None

            if response:
                if qnode_measure["weight"] != 0:
                    percentage = response["score"] / response["weight"]
                else:
                    percentage = None
                comment = response["comment"]
                if response["not_relevant"]:
                    not_relevant = "Yes"
                else:
                    not_relevant = "No"
            else:
                percentage = None
                comment = None
                not_relevant = None

            numbering = prefix + str(qnode_measure["seq"] + 1) + ". "
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(
                self.line, 1, numbering + qnode_measure["title"], format_bold_header)

            # Hide some columns from certain users
            if user_role in {'clerk', 'org_admin'}:
                weight = None
            else:
                weight = qnode_measure["weight"]

            if user_role == 'clerk':
                score = None
            else:
                score = percentage

            worksheet.write(self.line, 2, weight, format)
            worksheet.write(self.line, 3, score, format_percent)

            self.line = self.line + 1
            worksheet.write(self.line, 0, "Description", format_header)
            worksheet.write(self.line, 1, qnode_measure["description"], format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(self.line, 1, '', format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(self.line, 1, '', format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, '', format_header)
            worksheet.write(self.line, 1, '', format)
            worksheet.write(self.line, 2, '', format)
            self.line = self.line + 1
            worksheet.write(self.line, 0, "Comments", format_header_end)
            worksheet.write(self.line, 1, comment, format_end1)
            worksheet.write(self.line, 2, "Not Relevant", format_end2)
            worksheet.write(self.line, 3, not_relevant, format_end3)
            # answer option
            rt = qnode_measure['response_type']
            parts_len = len(rt.parts)
            index = 0
            for part in rt.parts:
                if 'name' in part:
                    worksheet.write(self.line - parts_len + index, 2,
                                    part["name"], format_part)
                index = index + 1

            index = 0
            if response and response["response_parts"] and not response["not_relevant"]:
                for part in response["response_parts"]:
                    if 'index' in part:
                        answer = "%d - %s" % (part['index'] + 1, part['note'])
                    else:
                        answer = part['value']
                    worksheet.write(self.line - parts_len + index, 3,
                                    answer, format_part_answer)
                    index = index + 1
            else:
                for i in range(0, parts_len):
                    worksheet.write(self.line - parts_len + index, 3,
                                    '', format_part_answer)
                    index = index + 1

            self.line = self.line + 1

    def process_tabular(
            self, file_name, program_id, survey_id, submission_id,
            user_role, base_url):
        """
        Open and write an Excel file
        """
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet('Response')
        worksheet_metadata = workbook.add_worksheet('Metadata')

        format = workbook.add_format()
        format.set_text_wrap()
        format_no_wrap = workbook.add_format()
        format_comment = workbook.add_format()
        format_comment.set_text_wrap()
        format_no_wrap = workbook.add_format()
        format_percent = workbook.add_format()
        format_percent.set_num_format(10)
        format_int = workbook.add_format()
        format_int.set_num_format(1)
        format_date = workbook.add_format({'num_format': 'dd/mmm/yy'})
        format_2_decimal = workbook.add_format({'num_format': '0.00'})
        url_format = workbook.add_format({
            'font_color': 'blue',
            'underline':  1
        })

        line = 1
        with model.session_scope() as session:
            survey = (session.query(model.Survey)
                .get((survey_id, program_id)))

            if not survey:
                raise errors.MissingDocError("No such survey")

            if not 'levels' in survey.structure:
                raise errors.InternalModelError("Survey is misconfigured")

            if submission_id:
                submission = (session.query(model.Submission)
                    .get(submission_id))
                if submission.survey_id != survey.id:
                    raise errors.MissingDocError(
                        "That submission does not belong to that survey")
                self.write_metadata(workbook, worksheet_metadata, submission)
            else:
                submission = None

            levels = survey.structure["levels"]
            level_length = len(levels)
            worksheet.set_column(0, level_length, 50)

            measures = [qm.measure for qm in survey.ordered_qnode_measures]

            max_parts = 0
            longest_response_type = None
            for m in measures:
                if len(m.response_type.parts) > max_parts:
                    longest_response_type = m.response_type
                    max_parts = len(m.response_type.parts)

            if longest_response_type:
                response_parts = [
                    p.get('name') or "Part %s" % string.ascii_uppercase[i]
                    for i, p in enumerate(longest_response_type.parts)]
            else:
                response_parts = []

            worksheet.set_column(level_length + 1,
                level_length + max_parts + 11, 15)
            worksheet.set_column(level_length + max_parts + 12,
                level_length + max_parts + 12, 100)

            # Header from heirarchy levels
            self.write_response_header(
                workbook, worksheet, levels, max_parts, response_parts)

            for measure in measures:
                qnode_measure = measure.get_qnode_measure(survey)
                self.write_qnode(
                    worksheet, qnode_measure.qnode, line, format, level_length - 1)

                seq = qnode_measure.seq + 1

                worksheet.write(
                    line, level_length, "%d. %s" % (seq, measure.title), format)

                importance = None
                urgency = None
                if submission:
                    response = model.Response.from_measure(
                        qnode_measure, submission)
                    url = base_url + "/#/3/measure/{}?submission={}".format(
                        measure.id, submission.id)

                    # Walk up the tree to get the importance and target from the
                    # parent rnodes
                    parent = qnode_measure.qnode
                    while parent and (importance is None or urgency is None):
                        rnode = model.ResponseNode.from_qnode(parent, submission)
                        if rnode is not None:
                            if importance is None:
                                importance = rnode.importance
                            if urgency is None:
                                urgency = rnode.urgency
                        parent = parent.parent

                else:
                    response = None
                    url = base_url + '/#/3/measure/{}?program={}&survey={}'.format(
                        measure.id, program_id, qnode_measure.survey_id)

                worksheet.write(
                line, level_length + max_parts + 1, importance, format_int)
                worksheet.write(
                line, level_length + max_parts + 2, urgency, format_int)

                score = None
                comment = ''
                quality = None
                self.comment = ''
                if response:
                    if not response.not_relevant:
                        self.write_response_parts(
                            worksheet, response.response_parts, line,
                            format_no_wrap, level_length + 1)

                    export_approval_status = ['final', 'reviewed', 'approved']

                    self.write_approval(
                        worksheet, line,
                        level_length + max_parts + 2, response,
                        response.user, format, format_date)
                    if response.approval in export_approval_status:
                        export_approval_status.remove(response.approval)

                    for approval_status in export_approval_status:
                        res = (session.query(model.ResponseHistory)
                            .filter_by(submission_id=response.submission_id,
                                measure_id=response.measure_id,
                                approval=approval_status)
                            .order_by(model.ResponseHistory.modified.desc())
                            .first())
                        if res:
                            user = session.query(model.AppUser).\
                                filter_by(id=res.user_id).\
                                first()

                            self.write_approval(worksheet, line,
                                level_length + max_parts + 2, res,
                                user, format, format_date)

                    if user_role != 'clerk':
                        if response.measure.weight != 0:
                            score = response.score #/ response.measure.weight
                        else:
                            score = 0
                    if response.comment or submission_id:
                       comment = response.comment + '; '
                    quality = response.quality

                if user_role in {'clerk', 'org_admin'}:
                    weight = None
                else:
                    weight = measure.weight

                worksheet.write(
                        line, level_length + max_parts + 9,
                        score, format_2_decimal)
                #        score, format_percent)
                worksheet.write(
                        line, level_length + max_parts + 10,
                        weight, format_no_wrap)
                worksheet.write(
                        line, level_length + max_parts + 11,
                        quality, format_no_wrap)
                worksheet.write(
                        line, level_length + max_parts + 12,
                        comment + self.comment , format_comment)
                        #comment, format_comment)

                worksheet.write_url(line, level_length + max_parts + 13,
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



    def write_metadata(self, workbook, sheet, submission):
        sheet.set_column(0, 1, 40)

        line = 0
        format = workbook.add_format()
        format.set_text_wrap()
        format_header = workbook.add_format()
        format_header.set_text_wrap()
        format_header.set_bold()
        log.info("submission: %s", submission.title)

        sheet.write(line, 0, "Program Name", format_header)
        sheet.write(line, 1, submission.program.title, format)
        line = line + 1
        sheet.write(line, 0, "Survey Name", format_header)
        sheet.write(line, 1, submission.survey.title, format)
        line = line + 1
        sheet.write(line, 0, "Organisation", format_header)
        sheet.write(line, 1, submission.organisation.name, format)
        line = line + 1
        sheet.write(line, 0, "Submission Name", format_header)
        sheet.write(line, 1, submission.title, format)
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
        sheet.write(0, len(levels) + max_response + 1, "Importance", format)
        #sheet.write(0, len(levels) + max_response + 2, "Urgency", format)
        sheet.write(0, len(levels) + max_response + 2, "Target Level", format)
        sheet.write(0, len(levels) + max_response + 3, "Final Report By", format)
        sheet.write(0, len(levels) + max_response + 4, "Final Report Date", format)
        sheet.write(0, len(levels) + max_response + 5, "Review By", format)
        sheet.write(0, len(levels) + max_response + 6, "Reviewed Date", format)
        sheet.write(0, len(levels) + max_response + 7, "Approved By", format)
        sheet.write(0, len(levels) + max_response + 8, "Approved Date", format)

        sheet.write(0, len(levels) + max_response + 9, "Score", format)
        sheet.write(0, len(levels) + max_response + 10, "Weight", format)
        sheet.write(0, len(levels) + max_response + 11, "Quality", format)
        sheet.write(0, len(levels) + max_response + 12, "Comment", format)
        sheet.write(0, len(levels) + max_response + 13, "URL", format)

    def write_qnode(self, sheet, qnode, line, format, col):
        if qnode.parent != None:
            self.write_qnode(sheet, qnode.parent, line, format, col - 1)
        sheet.write(line, col, str(qnode.seq + 1) + ". " + qnode.title, format)

    #def write_response_parts(self, sheet, parts, line, format, col):
    #    if parts != None:
    #        for part in parts:
    #            if 'index' in part:
    #                sheet.write(
    #                    line, col, "%d - %s" % (part["index"] + 1, part["note"]),
    #                    format)
    #            else:
    #                sheet.write(line, col, "%s" % part["value"], format)
    #            col = col + 1
    #    return col

    def write_response_parts(self, sheet, parts, line, format, col):
        smIdx = 1
        if parts != None:
            for part in parts:
                if 'comment' in part:
                    comment=''
                    if part["comment"] and part["comment"] != '':
                        comment = part["comment"]                   
                    self.comment= self.comment  + comment + '; '
                    smIdx = smIdx + 1
                if 'index' in part:
                    sheet.write(
                        line, col, "%d - %s" % (part["index"] + 1, part["note"]),
                        format)
                else:
                    sheet.write(line, col, "%s" % part["value"], format)
                col = col + 1
        return col
