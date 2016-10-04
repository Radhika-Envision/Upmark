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
MIN_CONSITUENTS = 5

log = logging.getLogger('app.report.temporal')


class TemporalReportHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, survey_id, extension):

        parameters = self.request_son
        organisation_id = parameters.get('organisation_id')

        try:
            parameters['min_constituents'] = int(
                parameters.get('min_constituents', MIN_CONSITUENTS))
        except ValueError:
            raise handlers.ModelError("Invalid minimum number of constituents")

        if parameters['min_constituents'] < MIN_CONSITUENTS:
            if not self.has_privillege('admin'):
                raise handlers.ModelError(
                    "You can't generate a report with so few consituents")

        if parameters.get('type') != 'summary':
            if not self.has_privillege('consultant'):
                raise handlers.ModelError("You can't generate a detailed report")

        with tempfile.TemporaryDirectory() as tmpdir:
            outpath, outfile = yield self.process_temporal(
                parameters, survey_id, tmpdir, extension)

            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header(
                'Content-Disposition', 'attachment; filename=%s' % outfile)

            with open(outpath, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    @run_on_executor
    def process_temporal(self, parameters, survey_id, tmpdir, extension):
        with model.session_scope() as session:
            query = self.build_query(session, parameters, survey_id)
            responses = query.all()
            table_meta = self.bucket_responses(responses, self.get_interval(parameters))
            cols, rows = self.create_detail_table(table_meta)

            if parameters.get('type') == 'summary':
                report_type = 'summary'
                cols, rows = self.convert_to_stats(
                    cols, rows, parameters['organisation_id'],
                    parameters['min_constituents'])
            else:
                report_type = 'detail'

            cols, rows = self.convert_to_primitives(cols, rows)

        if extension == 'xlsx':
            outfile = "%s.xlsx" % report_type
            outpath = os.path.join(tmpdir, outfile)
            self.write_xlsx(cols, rows, outpath)
        else:
            raise handlers.MissingDocError(
                "File type not supported: %s" % extension)

        return outpath, outfile

    def build_query(self, session, parameters, survey_id):
        # All responses to current survey
        query = (session.query(model.Response)
                .options(joinedload('submission'))
                .options(joinedload('submission.organisation'))
                .options(joinedload('qnode_measure'))
                .join(model.Submission)
                .join(model.Survey)
                .join(model.Organisation)
                .filter(model.Submission.survey_id == survey_id)
                .filter(~model.Submission.deleted)
                .filter(~model.Survey.deleted)
                .order_by(model.Response.measure_id,
                    model.Submission.organisation_id,
                    model.Submission.created))

        def date_filter(query):
            interval = self.get_interval(parameters)
            min_date = self.lower_bound(
                datetime.datetime.utcfromtimestamp(parameters.get('min_date')),
                interval)
            max_date = self.upper_bound(
                datetime.datetime.utcfromtimestamp(parameters.get('max_date')),
                interval)

            self.reason("Date range: %s - %s" % (
                min_date.strftime('%d %b %Y'),
                max_date.strftime('%d %b %Y')))

            return (query
                .filter(model.Submission.created >= min_date)
                .filter(model.Submission.created < max_date))

        def quality_filter(query):
            quality = parameters.get('quality')
            return query.filter(model.Response.quality >= quality)

        def approval_filter(query):
            approval = parameters.get('approval', 'reviewed')
            approval_states = ['draft', 'final', 'reviewed', 'approved']
            approval_index = approval_states.index(approval)
            if self.has_privillege('admin'):
                min_approval = approval_states.index('draft')
            else:
                min_approval = approval_states.index('reviewed')
            if approval_index < min_approval:
                raise handlers.ModelError(
                    "You can't generate a report for that approval state")
            included_approval_states=approval_states[approval_index:]
            return query.filter(
                model.Submission.approval.in_(included_approval_states))

        def location_filter(query):
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
            return query.filter(union_loc_filter)

        def size_filter(query):
            query = query.join(model.OrgMeta)

            if parameters.get('min_internal_ftes'):
                min_ftes = parameters.get('min_internal_ftes')
                query = query.filter(
                    model.OrgMeta.number_fte >= min_ftes)
            if parameters.get('max_internal_ftes'):
                max_ftes = parameters.get('max_internal_ftes')
                query = query.filter(
                    model.OrgMeta.number_fte <= max_ftes)

            if parameters.get('min_external_ftes'):
                min_ftes = parameters.get('min_external_ftes')
                query = query.filter(
                    model.OrgMeta.number_fte_ext >= min_ftes)
            if parameters.get('max_external_ftes'):
                max_ftes = parameters.get('max_external_ftes')
                query = query.filter(
                    model.OrgMeta.number_fte_ext <= max_ftes)

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

            if parameters.get('min_population'):
                min_population = parameters.get('min_population')
                query = query.filter(
                    model.OrgMeta.population_served >= min_population)
            if parameters.get('max_population'):
                max_population = parameters.get('max_population')
                query = query.filter(
                    model.OrgMeta.population_served <= max_employees)

            return query

        query = date_filter(query)
        query = approval_filter(query)
        if parameters.get('quality'):
            query = quality_filter(query)
        if parameters.get('locations'):
            query = location_filter(query)
        if parameters.get('filter_size'):
            query = size_filter(query)
        return query

    def bucket_responses(self, responses, interval):
        class TableMeta:
            def keys(self):
                return itertools.product(
                    self.qnode_measures, self.organisations, self.buckets)

        tm = TableMeta()
        tm.bucketed_responses = {}
        buckets = set()
        qnode_measures = set()
        organisations = set()

        for response in responses:
            bucket = self.lower_bound(response.submission.created, interval)
            k = (response.measure_id, response.submission.organisation,
                bucket)

            if k in tm.bucketed_responses:
                if (tm.bucketed_responses[k].submission.created
                        > response.submission.created):
                    continue

            tm.bucketed_responses[k] = response

            buckets.add(bucket)
            qnode_measures.add(response.qnode_measure)
            organisations.add(response.submission.organisation)

        tm.buckets = sorted(buckets)
        tm.qnode_measures = sorted(qnode_measures, key=lambda m: m.get_path_tuple())
        tm.organisations = sorted(organisations, key=lambda o: o.name)
        return tm

    def create_detail_table(self, table_meta):
        rows = []
        current_row = None
        current_measure_id = None
        current_organisation = None
        latest_response = None
        initial = True
        for qm, organisation, bucket in table_meta.keys():
            k = (qm.measure_id, organisation, bucket)
            r = table_meta.bucketed_responses.get(k)
            if qm.measure_id != current_measure_id or organisation != current_organisation:
                # New row, write url metadata for previous row before reset
                if not initial:
                    current_row[2] = latest_response
                    latest_response = None

                current_measure_id = qm.measure_id
                current_organisation = organisation
                current_row = [qm, organisation, None]
                rows.append(current_row)
                initial = False

            current_row.append(None or r and r.score)
            if r:
                latest_response = r

        # write url metadata for last row
        if current_row:
            current_row[2] = latest_response

        cols = [
            ("Path", 10, 'text'),
            ("Measure", 20, 'text'),
            ("Organisation", 20, 'text'),
            ("Link", 5, 'link'),
        ] + [(b, 12, 'score') for b in table_meta.buckets]

        return cols, rows

    def convert_to_stats(self, cols, rows, organisation_id, min_constituents):
        out_rows = []
        for m, rs in itertools.groupby(rows, key=lambda r: r[0]):
            rs = list(rs)
            cells = list(zip(*rs))
            stats = [self.compute_stats(c, min_constituents) for c in cells[3:]]
            stats = list(zip(*stats))
            try:
                org_row = next(r for r in rs if str(r[1].id) == organisation_id)
            except StopIteration:
                org_row = [None] * 3
            out_rows.append([m, "Self score", org_row[2]] + org_row[3:])
            out_rows.append([m, "Min", None] + list(stats[0]))
            out_rows.append([m, "1st Quartile", None] + list(stats[1]))
            out_rows.append([m, "Median", None] + list(stats[2]))
            out_rows.append([m, "3rd Quartile", None] + list(stats[3]))
            out_rows.append([m, "Max", None] + list(stats[4]))

            # Report on statistics instead of organisations
        out_cols = cols[:]
        out_cols[2] = ("Statistic", 12, 'text')

        return out_cols, out_rows

    def compute_stats(self, cells, min_constituents):
        constituents = [c for c in cells if c is not None]
        if len(constituents) < min_constituents:
            return (None,) * 5
        np_columns = numpy.array(constituents)
        results = (min(np_columns),
                    numpy.percentile(np_columns, 25),
                    numpy.percentile(np_columns, 50),
                    numpy.percentile(np_columns, 75),
                    max(np_columns))

        return results

    def convert_to_primitives(self, cols, rows):
        out_rows = []
        for row in rows:
            qm, stat, latest_response = row[0:3]
            scores = row[3:]
            out_rows.append([
                qm.get_path(),
                qm.measure.title,
                isinstance(stat, model.Organisation) and stat.name or stat,
                self.get_url(qm, stat, latest_response),
            ] + scores)
        out_cols = cols[:]
        return out_cols, out_rows

    def write_xlsx(self, cols, rows, outpath):
        with xlsxwriter.Workbook(outpath) as workbook:
            worksheet = workbook.add_worksheet("Data")

            cell_formats = {
                'text_header': workbook.add_format({'bold': 1}),
                'date_header': workbook.add_format(
                    {'num_format': 'dd/mm/yyyy', 'bold': 1}),
                'text': workbook.add_format({}),
                'link': workbook.add_format(
                    {'font_color': 'blue', 'underline':  1}),
                'score': workbook.add_format({}),
            }

            # Write column headings
            for i, col in enumerate(cols):
                heading, cell_width, data_type = col
                if isinstance(heading, datetime.datetime):
                    header_format = cell_formats['date_header']
                else:
                    header_format = cell_formats['text_header']
                worksheet.set_column(i, i, cell_width, cell_formats[data_type])
                worksheet.write(0, i, heading, header_format)

            # Write data, this depends on requested report type.
            for row_index, row in enumerate(rows):
                row_index += 1
                for col_index, (col, cell) in enumerate(zip(cols, row)):
                    if col[2] == 'link':
                        worksheet.write(
                            row_index, col_index, cell, None, "Link")
                    else:
                        worksheet.write(row_index, col_index, cell)

    def get_url(self, qm, statistic, response):
        base_url = "%s://%s" % (self.request.protocol, self.request.host)
        if response:
            return "{}/#/2/measure/{}?submission={}".format(
                base_url, response.measure_id, response.submission.id)
        elif qm:
            return "{}/#/2/measure/{}?program={}&survey={}".format(
                base_url, qm.measure_id, qm.program_id, qm.survey_id)
        else:
            return None

    def get_interval(self, parameters):
        try:
            width = int(parameters.get('interval_num', 1))
        except ValueError:
            raise handlers.ModelError("Invalid interval")
        units = parameters.get('interval_unit', 'months')

        if units == 'years':
            if width < 1:
                raise handlers.ModelError("Interval must be at least one year")
        elif units == 'months':
            if width not in {1, 2, 3, 6}:
                raise handlers.ModelError("Interval must be 1, 2, 3 or 6 months")
        else:
            raise handlers.ModelError("Unrecognised interval %s" % unit)
        return width, units

    def temporal_bucket(self, date, interval):
        width, unit = interval
        # Align buckets to Gregorian epoch
        if unit == 'years':
            return date.year // width
        else:
            return (date.year * 12 + (date.month - 1)) // width

    def lower_bound_of_bucket(self, bucket_i, interval):
        width, unit = interval
        if unit == 'years':
            year = bucket_i * width
            return datetime.datetime(year, 1, 1)
        else:
            year = (bucket_i * width) // 12
            month = ((bucket_i * width) % 12) + 1
            return datetime.datetime(year, month, 1)

    def lower_bound(self, date, interval):
        bucket_i = self.temporal_bucket(date, interval)
        return self.lower_bound_of_bucket(bucket_i, interval)

    def upper_bound(self, date, interval):
        bucket_i = self.temporal_bucket(date, interval)
        bucket_i += 1
        return self.lower_bound_of_bucket(bucket_i, interval)

    def date_diff(self, date, today):
        this_year = today.year
        this_month = today.month
        month = date.month
        year = date.year

        delta_months = 0
        delta_years = 0
        while ((month != this_month) or (year != this_year)):
            month += 1
            if month == 13:
                month = 1
                year += 1
                delta_years += 1

            delta_months += 1

        return (delta_months, delta_years)
