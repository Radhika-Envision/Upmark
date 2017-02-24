from concurrent.futures import ThreadPoolExecutor
import datetime
import itertools
import logging
import os
import tempfile

import numpy as np
from sqlalchemy import true, false
from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.concurrent import run_on_executor
import tornado.web
import xlsxwriter

import handlers
import model
from utils import keydefaultdict

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
            if not self.has_privillege('consultant'):
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
            responses = self.filter_deleted_structure(responses)
            interval = Interval.from_parameters(parameters)
            bucketer = TemporalResponseBucketer(interval)
            for response in responses:
                bucketer.add(response)
            table_meta = bucketer.to_table_meta()
            rows = self.create_detail_rows(table_meta)

            if parameters.get('type') == 'summary':
                report_type = 'summary'
                organisation = (session
                    .query(model.Organisation)
                    .get(parameters['organisation_id']))
                rows = self.convert_to_stats(
                    rows, organisation, parameters['min_constituents'])
            else:
                report_type = 'detail'

            cols, rows = self.create_table(rows, table_meta, report_type)

        if extension == 'xlsx':
            outfile = "%s.xlsx" % report_type
            outpath = os.path.join(tmpdir, outfile)
            writer = XlWriter(outpath)
        else:
            raise handlers.MissingDocError(
                "File type not supported: %s" % extension)
        writer.write(cols, rows)

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
            interval = Interval.from_parameters(parameters)
            min_date = interval.lower_bound(
                datetime.datetime.utcfromtimestamp(parameters.get('min_date')))
            max_date = interval.upper_bound(
                datetime.datetime.utcfromtimestamp(parameters.get('max_date')))

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
            if self.has_privillege('consultant'):
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

    def filter_deleted_structure(self, responses):
        deleted_things = keydefaultdict(
            lambda t: t.closest_deleted_ancestor() is not None)
        return [r for r in responses if not deleted_things[r.qnode_measure]]

    def create_detail_rows(self, table_meta):
        '''
        @return a list of OrganisationRows. These need further transformation
            before they can be rendered; see OrganisationRow for details. The
            rows are sorted in the same way as the keys in `table_meta`.
        '''
        rows = []
        current_row = None
        n_buckets = len(table_meta.buckets)
        for qm, organisation, bucket in table_meta.keys():
            k = (qm.measure_id, organisation, bucket)
            response = table_meta.get(k)
            if (not current_row
                    or qm.measure_id != current_row.qm.measure_id
                    or organisation != current_row.organisation):
                # New row
                current_row = OrganisationRow(qm, organisation)
                rows.append(current_row)

            if response is not None:
                current_row.append(response)
                current_row.response = response
            else:
                current_row.append(None)

        return rows

    def convert_to_stats(self, rows, organisation, min_constituents):
        out_rows = []
        for qm, qm_rows in itertools.groupby(rows, key=lambda r: r.qm):
            qm_rows = list(qm_rows)

            row_scores = [row.scores for row in qm_rows]
            cells = list(zip(*row_scores))
            stats = [self.compute_stats(c, min_constituents) for c in cells]
            stats = list(zip(*stats))
            try:
                out_rows.append(next(
                    row for row in qm_rows
                    if row.organisation == organisation))
            except StopIteration:
                out_rows.append(OrganisationRow(qm, organisation))
            out_rows.append(StatisticRow(qm, "Min", list(stats[0])))
            out_rows.append(StatisticRow(qm, "1st Quartile", list(stats[1])))
            out_rows.append(StatisticRow(qm, "Median", list(stats[2])))
            out_rows.append(StatisticRow(qm, "3rd Quartile", list(stats[3])))
            out_rows.append(StatisticRow(qm, "Max", list(stats[4])))
            out_rows.append(StatisticRow(qm, "Consituents", list(stats[5])))

        return out_rows

    def compute_stats(self, cells, min_constituents):
        constituents = [c for c in cells if c is not None]
        if len(constituents) < min_constituents:
            return (None,) * 5 + (0,)
        np_columns = np.array(constituents)
        results = (
            min(np_columns),
            np.percentile(np_columns, 25),
            np.percentile(np_columns, 50),
            np.percentile(np_columns, 75),
            max(np_columns),
            len(constituents),
        )

        return results

    def create_table(self, rows, table_meta, report_type):
        base_url = "%s://%s" % (self.request.protocol, self.request.host)
        out_rows = []
        for row in rows:
            header_cells = [
                row.qm.program.title,
                row.qm.get_path(),
                row.qm.measure.title,
                row.name,
                row.link(base_url),
            ]
            for title, cells in zip(row.sub_titles(), row.sub_rows()):
                out_rows.append(header_cells + [title] + cells)

        if report_type == 'detail':
            statistic_name = "Organisation"
        else:
            statistic_name = "Statistic"
        cols = [
            ("Latest program", 15, 'text'),
            ("Path", 10, 'text'),
            ("Measure", 40, 'text'),
            (statistic_name, 30, 'text'),
            ("Link", 8, 'link'),
            ("Part", 20, 'text'),
        ] + [(b, 12, 'real') for b in table_meta.buckets]

        return cols, out_rows


class XlWriter:
    def __init__(self, outpath):
        self.outpath = outpath

    def write(self, cols, rows):
        with xlsxwriter.Workbook(self.outpath) as workbook:
            self.write_(cols, rows, workbook)

    def write_(self, cols, rows, workbook):
        worksheet = workbook.add_worksheet("Data")
        worksheet.freeze_panes(1, 0)

        cell_formats = {
            'text_header': workbook.add_format({'bold': 1}),
            'date_header': workbook.add_format(
                {'num_format': 'dd/mm/yyyy', 'bold': 1}),
            'text': workbook.add_format({}),
            'link': workbook.add_format(
                {'font_color': 'blue', 'underline':  1}),
            'real': workbook.add_format(
                {'num_format': '0.00'}),
            'int': workbook.add_format(
                {'num_format': '0'}),
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
                if isinstance(cell, Link):
                    worksheet.write_url(
                        row_index, col_index, cell.url, None, cell.title)
                elif isinstance(cell, int) and col[2] != 'int':
                    worksheet.write(
                        row_index, col_index, cell, cell_formats['int'])
                else:
                    worksheet.write(row_index, col_index, cell)


class Interval:
    def __init__(self, width, units):
        self.width = width
        self.units = units

    @classmethod
    def from_parameters(cls, parameters):
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
            raise handlers.ModelError("Unrecognised interval %s" % units)
        return cls(width, units)

    def temporal_bucket(self, date):
        # Align buckets to Gregorian epoch
        if self.units == 'years':
            return date.year // self.width
        else:
            return (date.year * 12 + (date.month - 1)) // self.width

    def lower_bound_of_bucket(self, bucket_i):
        if self.units == 'years':
            year = bucket_i * self.width
            return datetime.datetime(year, 1, 1)
        else:
            year = (bucket_i * self.width) // 12
            month = ((bucket_i * self.width) % 12) + 1
            return datetime.datetime(year, month, 1)

    def lower_bound(self, date):
        bucket_i = self.temporal_bucket(date)
        return self.lower_bound_of_bucket(bucket_i)

    def upper_bound(self, date):
        bucket_i = self.temporal_bucket(date)
        bucket_i += 1
        return self.lower_bound_of_bucket(bucket_i)


class TableMeta:
    '''
    Bucketed responses sorted by measure, organisation and time.
    '''

    def __init__(self, bucketed_responses, qnode_measures, organisations, buckets):
        self.bucketed_responses = bucketed_responses
        self.qnode_measures = qnode_measures
        self.organisations = organisations
        self.buckets = buckets

    def keys(self):
        return itertools.product(
            self.qnode_measures, self.organisations, self.buckets)

    def __getitem__(self, k):
        return self.bucketed_responses[k]

    def get(self, k):
        return self.bucketed_responses.get(k)

    def __iter__(self):
        return iter(keys(self))

    def __len__(self):
        return len(self.bucketed_responses)


class TemporalResponseBucketer:
    '''
    Buckets responses by measure, organisation and time.
    '''

    def __init__(self, interval):
        self.interval = interval
        self.bucketed_responses = {}
        self.buckets = set()
        self.qnode_measure_map = {}
        self.organisations = set()

    def add(self, response):
        bucket = self.interval.lower_bound(response.submission.created)
        k = (response.measure_id, response.submission.organisation,
            bucket)

        if k in self.bucketed_responses:
            if (self.bucketed_responses[k].submission.created
                    > response.submission.created):
                return

        self.bucketed_responses[k] = response

        self.buckets.add(bucket)
        self.qnode_measure_map[response.measure_id] = response.qnode_measure
        self.organisations.add(response.submission.organisation)

    def to_table_meta(self):
        buckets = sorted(self.buckets)
        qnode_measures = sorted(
            self.qnode_measure_map.values(), key=lambda qm: qm.get_path_tuple())
        organisations = sorted(
            self.organisations, key=lambda o: o.name)
        return TableMeta(
            self.bucketed_responses.copy(), qnode_measures, organisations, buckets)


class OrganisationRow:
    __slots__ = 'qm organisation response responses'.split()

    def __init__(self, qm, organisation):
        self.qm = qm
        self.organisation = organisation
        self.response = None
        self.responses = []

    def append(self, response):
        self.responses.append(response)

    def sub_titles(self):
        yield "Score"

    def sub_rows(self):
        yield [
            response.score if response is not None else None
            for response in self.responses]

    @property
    def name(self):
        return self.organisation.name

    def link(self, base_url):
        if self.response:
            return Link(
                'Response',
                "{}/#/2/measure/{}?submission={}".format(
                    base_url, self.response.measure_id,
                    self.response.submission.id))
        elif self.qm:
            return Link(
                'Measure',
                "{}/#/2/measure/{}?program={}&survey={}".format(
                    base_url, self.qm.measure_id, self.qm.program_id,
                    self.qm.survey_id))
        else:
            return None


class StatisticRow:
    __slots__ = 'qm name scores'.split()

    def __init__(self, qm, name, scores):
        self.qm = qm
        self.name = name
        self.scores = scores

    def link(self, base_url):
        if self.qm:
            return Link(
                'Measure',
                "{}/#/2/measure/{}?program={}&survey={}".format(
                    base_url, self.qm.measure_id, self.qm.program_id,
                    self.qm.survey_id))
        else:
            return None


class Link:
    __slots__ = ('title', 'url')

    def __init__(self, title, url):
        self.title = title
        self.url = url
