from concurrent.futures import ThreadPoolExecutor
import datetime
import itertools
import logging
import os
import tempfile

import numpy
from sqlalchemy import true, false
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
                    .join(model.Survey)
                    .join(model.Organisation)
                    .filter(model.Submission.survey_id == survey_id)
                    .filter(~model.Submission.deleted)
                    .filter(~model.Survey.deleted)
                    .order_by(model.Response.measure_id,
                        model.Submission.organisation_id,
                        model.Submission.created))

            # Date filter
            min_date = (datetime.datetime
                .fromtimestamp(parameters.get('min_date')))
            max_date = (datetime.datetime
                .fromtimestamp(parameters.get('max_date')))
            query = query.filter(model.Submission.created > min_date)
            query = query.filter(model.Submission.created < max_date)

            interval = [parameters.get('interval_num'),
                parameters.get('interval_unit')]

            # Response quality filter
            if parameters.get('quality'):
                quality = parameters.get('quality')
                query = query.filter(model.Response.quality >= quality)

            # Submission approval state filter
            if parameters.get('approval'):
                approval = parameters.get('approval')
                approval_states = ['draft', 'final', 'reviewed', 'approved']
                approval_index = approval_states.index(approval)
                if approval_index < 2:
                    raise handlers.ModelError(
                        "Can't generate a report for that approval state")
                included_approval_states=approval_states[approval_index:]

                query = query.filter(
                    model.Submission.approval.in_(included_approval_states))

            # Location filter
            if parameters.get('locations'):
                locations = parameters.get('locations')

                query = query.join(model.OrgLocation)
                union_loc_filter = false()

                for loc in locations:
                    loc_filter = true()
                    if loc.get('country'):
                        loc_filter &= model.OrgLocation.country == loc.get('country')
                    if loc.get('state'):
                        loc_filter &= model.OrgLocation.state == loc.get('state')
                    if loc.get('region'):
                        loc_filter &= model.OrgLocation.region == loc.get('region')
                    if loc.get('county'):
                        loc_filter &= model.OrgLocation.county == loc.get('county')
                    if loc.get('city'):
                        loc_filter &= model.OrgLocation.city == loc.get('city')
                    if loc.get('postcode'):
                        loc_filter &= model.OrgLocation.postcode == loc.get('postcode')
                    if loc.get('suburb'):
                        loc_filter &= model.OrgLocation.suburb == loc.get('suburb')
                    union_loc_filter |= loc_filter
                query = query.filter(union_loc_filter)

            # Size filter
            if parameters.get('filter_size'):
                query = query.join(model.OrgMeta)

                if parameters.get('min_ftes'):
                    min_ftes = parameters.get('min_ftes')
                    query = query.filter(model.OrgMeta.number_fte >= min_ftes)
                if parameters.get('max_ftes'):
                    max_ftes = parameters.get('max_ftes')
                    query = query.filter(model.OrgMeta.number_fte <= max_ftes)
                if parameters.get('min_contractors'):
                    min_contractors = parameters.get('min_contractors')
                    query = query.filter(
                        model.OrgMeta.number_fte_ext >= min_contractors)
                if parameters.get('max_contractors'):
                    max_contractors = parameters.get('max_contractors')
                    query = query.filter(
                        model.OrgMeta.number_fte_ext <= max_contractors)
                if parameters.get('min_employees'):
                    min_employees = parameters.get('min_employees')
                    query = query.filter(
                        (model.OrgMeta.number_fte +
                            model.OrgMeta.number_fte_ext) >= min_employees)
                if parameters.get('max_employees'):
                    max_employees = parameters.get('max_employees')
                    query = query.filter(
                        (model.OrgMeta.number_fte +
                            model.OrgMeta.number_fte_ext) <= max_employees)

            responses = query.all()

            bucketed_responses = {}
            buckets = set()
            measures = set()
            organisations = set()
            for response in responses:
                bucket = self.lower_bound(response.submission.created, interval)
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
                r = bucketed_responses.get(k)
                measure, organisation, bucket = k
                if measure != current_measure or organisation != current_organisation:
                    current_measure = measure
                    current_organisation = organisation
                    current_row = [measure, organisation]
                    rows.append(current_row)
                current_row.append(r and r.score or None)

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
            cells = list(zip(*rs))
            stats = [self.compute_stats(c) for c in cells[2:]]
            stats = list(zip(*stats))
            org_row = [r for r in rs if str(r[1].id) == organisation_id][0]
            out_table.append([m, "Self score"] + org_row[2:])
            out_table.append([m, "Min"] + list(stats[0]))
            out_table.append([m, "1st Quartile"] + list(stats[1]))
            out_table.append([m, "Median"] + list(stats[2]))
            out_table.append([m, "3rd Quartile"] + list(stats[3]))
            out_table.append([m, "Max"] + list(stats[4]))

        return out_table

    def compute_stats(self, cells):
        constituents = [c for c in cells if c is not None]
        if len(constituents) < 5:
            return (None,) * 5
        np_columns = numpy.array(constituents)
        results = (min(np_columns),
                    numpy.percentile(np_columns, 25),
                    numpy.percentile(np_columns, 50),
                    numpy.percentile(np_columns, 75),
                    max(np_columns))

        return results

    def lower_bound(self, date, interval):
        value = interval[0]
        unit = interval[1]
        today = date.today()

        if unit == 'Years':
            this_year = today.year

            delta = (this_year - date.year) % value
            if (delta == 0):
                bucket_year = date.year
            else:
                bucket_year = date.year + delta

            return date.replace(year=bucket_year, month=1, day=1,
                hour=0, minute=0, second=0, microsecond=0)

        if unit == 'Months':
            this_month = today.month

            delta = (this_month - date.month) % value
            bucket_year = date.year
            if (delta == 0):
                bucket_month = date.month
            else:
                bucket_month = date.month + delta
                if bucket_month > 12:
                    bucket_month = bucket_month % 12
                    bucket_year += 1

            return date.replace(year=bucket_year, month=bucket_month, day=1,
                hour=0, minute=0, second=0, microsecond=0)
