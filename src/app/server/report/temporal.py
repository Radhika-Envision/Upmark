from concurrent.futures import ThreadPoolExecutor
import datetime
import itertools
import logging
import os
import tempfile

import numpy
from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.concurrent import run_on_executor
import tornado.web
import xlsxwriter

import handlers
import model

BUF_SIZE = 4096
MAX_WORKERS = 4

log = logging.getLogger('app.report.temporal')


class TemporalReportHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, survey_id, extension):

        parameters = self.request_son

        organisation_id = parameters.get('organisation_id')

        with model.session_scope() as session:
            if organisation_id:
                pass

            # All responses to current survey
            query = (session.query(model.Response)
                    .options(joinedload('submission'))
                    .options(joinedload('submission.organisation'))
                    .options(joinedload('measure'))
                    .join(model.Submission)
                    .filter(model.Submission.survey_id == survey_id)
                    .order_by(model.Response.measure_id,
                        model.Submission.organisation_id,
                        model.Submission.created))

            responses = query.all()

            bucketed_responses = {}
            buckets = set()
            measures = set()
            organisations = set()
            for response in responses:
                bucket = self.lower_bound(response.submission.created)
                k = (response.measure, response.submission.organisation,
                    bucket)

                if k in bucketed_responses:
                    if (bucketed_responses[k].submission.created
                            > response.submission.created):
                        continue

                bucketed_responses[k] = response

                buckets.add(bucket)
                measures.add(response.measure)
                organisations.add(response.submission.organisation)

            buckets = sorted(buckets)
            measures = sorted(measures, key=lambda m: m.get_path(survey_id))
            organisations = sorted(organisations, key=lambda o: o.name)

            rows = []
            current_row = None
            current_measure = None
            current_organisation = None
            for k in itertools.product(measures, organisations, buckets):
                r = bucketed_responses[k]
                if r.measure != current_measure or r.submission.organisation != current_organisation:
                    current_measure = r.measure
                    current_organisation = r.submission.organisation
                    current_row = [
                        r.measure,
                        r.submission.organisation]
                    rows.append(current_row)
                current_row.append(r.score)

            if organisation_id:
                rows = self.convert_to_stats(rows, organisation_id)

            columns = self.get_titles(buckets, organisation_id)

            # Export to csv/xls
            if organisation_id:
                outfile = "summary_report"
            else:
                outfile = "detailed_report"

            with tempfile.TemporaryDirectory() as tmpdir:
               output_path = os.path.join(tmpdir, outfile)

               yield self.export_data(columns, rows, tmpdir, outfile, extension, survey_id)

               self.set_header('Content-Type', 'application/octet-stream')
               self.set_header('Content-Disposition', 'attachment; filename='
                   + outfile + "." + extension)

               with open(output_path + "." + extension, 'rb') as f:
                   while True:
                       data = f.read(BUF_SIZE)
                       if not data:
                           break
                       self.write(data)

        self.finish()

    @run_on_executor
    def export_data(self, headings, data, outdir, outfile, filetype, survey_id):
            if filetype == "xlsx":
                filename = outfile + "." + filetype
                outpath = os.path.join(outdir, filename)
                workbook = xlsxwriter.Workbook(outpath)
                worksheet = workbook.add_worksheet("Data")

                # Format definitions
                bold = workbook.add_format({'bold': 1})

                # Write column headings
                for i, heading in enumerate(headings):
                    worksheet.write_string(0, i, heading, bold)

                # Write data, this depends on requested report type.
                for row_index, row_data in enumerate(data):
                    for col_index in range(len(row_data)):
                        if col_index == 0:
                            worksheet.write(row_index + 1, col_index,
                                row_data[col_index].title)
                        elif col_index == 1 and outfile == "detailed_report":
                            worksheet.write(row_index + 1, col_index,
                                row_data[col_index].name)
                        else:
                            worksheet.write(row_index + 1, col_index,
                                row_data[col_index])
                workbook.close()
            else:
                raise handlers.MissingDocError(
                    "File type not supported: %s" % extension)

    def get_titles(self, buckets, org_id):
        if org_id:
            headers = ["Measure", "Statistic"]
        else:
            headers = ["Measure", "Organisation"]

        for b in buckets:
            headers.append(b.strftime('%m/%d/%y'))

        return headers

    def convert_to_stats(self, in_table, organisation_id):
        out_table = []
        for m, rs in itertools.groupby(in_table, key=lambda r: r[0]):
            rs = list(rs)
            columns = list(zip(*rs))
            np_columns = [numpy.array(c) for c in columns[2:]]
            stats = [self.compute_stats(n) for n in np_columns]
            stats = list(zip(*stats))
            org_row = [r for r in rs if str(r[1].id) == organisation_id][0]
            out_table.append([m, "Self score"] + org_row[2:])
            out_table.append([m, "Min"] + list(stats[0]))
            out_table.append([m, "1st Quartile"] + list(stats[1]))
            out_table.append([m, "Median"] + list(stats[2]))
            out_table.append([m, "3rd Quartile"] + list(stats[3]))
            out_table.append([m, "Max"] + list(stats[4]))

        return out_table

    def compute_stats(self, data):
        results = (min(data),
                    numpy.percentile(data, 25),
                    numpy.percentile(data, 50),
                    numpy.percentile(data, 75),
                    max(data))

        return results


    def lower_bound(self, date):
        return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
